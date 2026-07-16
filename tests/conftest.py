"""
tests/conftest.py — shared pytest configuration and fixtures.

Test tiers
----------

  Unit (default)
      Pure function / module tests.  No subprocesses.  No AI calls.  Fast.
      Run with: pytest

  Slow  (@pytest.mark.slow)
      Spawn real subprocesses but make NO AI calls (use fixture JSON or
      --help / --dry-run patterns).  Catches CLI-level structural bugs that
      unit tests miss (e.g. NameError in main(), argparse misconfiguration,
      broken imports through commands.py).  ~10-30 s.
      Run with: pytest --slow   or   pytest -m slow

  Live  (@pytest.mark.live)
      Spawn real subprocesses AND make real AI calls — but always with
      --cache enabled.  First run costs real money and populates the on-disk
      cache (~/.cross_api_cache/).  Every subsequent run is free and fast
      because responses are served from cache.
      Run with: pytest --live   or   pytest -m live

      Practical workflow:
        1. Run once on a machine with valid API keys:
               pytest --live          # populates cache
        2. Commit nothing extra — cache lives in ~/.cross_api_cache/.
        3. On any future run (CI, re-test, colleague's machine with same
           cache): pytest --live runs in <5 s per test, $0 cost.

      Use the pizza_dough or cross-stones fixtures so the prompts are
      short and deterministic.

Running all tiers at once:
    pytest --slow --live
"""
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make cross_st/ importable by its short module names (mmd_util, st_admin …)
# This mirrors what runpy.run_path does at runtime: it prepends the script's
# directory to sys.path so that sibling imports like `from mmd_util import …`
# resolve correctly.
# ---------------------------------------------------------------------------
_CROSS_AI = Path(__file__).parent.parent / "cross_st"
if str(_CROSS_AI) not in sys.path:
    sys.path.insert(0, str(_CROSS_AI))


# ─────────────────────────────────────────────────────────────────────────────
# AGT-1 / AGT-2 — module-level agent-registry seed
# ─────────────────────────────────────────────────────────────────────────────
#
# cross-ai-core 0.8.0 stopped auto-seeding built-in providers as
# self-agents.  On a fresh CI runner there is no ``~/.cross_ai_models.json``
# and no API keys, so ``get_ai_list()`` returns ``[]`` at module-import
# time of any test that captures it eagerly (e.g. tests/test_st_admin.py
# does ``AI_LIST = get_ai_list()`` at the top).
#
# The autouse ``_seed_legacy_agent_registry`` fixture below runs *per-test*
# and is therefore too late to fix that import-time capture.  We replicate
# the same seed at conftest module level — it executes once, before any
# test module is imported, so eager AI_LIST captures see the full provider
# set on CI just as they do on a developer machine.
import os as _os
import tempfile as _tempfile

_TMP_AGENTS = Path(_tempfile.mkdtemp(prefix="cross-test-agents-")) / "cross_ai_models.json"
# Set only the legacy env-var name.  cross-ai-core 0.8.0 reads
# CROSS_AI_AGENTS_FILE first, then CROSS_AI_AGENTS_FILE — by setting only
# the legacy name we leave the new-name slot free so individual tests can
# monkeypatch CROSS_AI_AGENTS_FILE to swap registries without our default
# winning over them.
_os.environ.setdefault("CROSS_AI_AGENTS_FILE", str(_TMP_AGENTS))

try:
    from cross_ai_core.agents import _AI_ALIASES, AgentSpec  # type: ignore
    from cross_ai_core.ai_handler import AI_LIST as _BUILTIN_AI_LIST  # type: ignore
    for _make in _BUILTIN_AI_LIST:
        _AI_ALIASES[_make] = AgentSpec(make=_make, model=None)

    # Persist the same seed to disk so subprocess-based tests (test_live.py,
    # test_integration.py, --slow tier) inherit a non-empty agent registry
    # via the CROSS_AI_AGENTS_FILE env var above.  Without this, subprocesses
    # see an empty agents file and reject `--agent openai` with
    # `--agent {}` (no valid choices).
    import json as _json
    _agents_payload = {
        "version": 2,
        "agents": {m: {"provider": m, "model": None} for m in _BUILTIN_AI_LIST},
        "_migrated_to_agents_v2": True,
    }
    _TMP_AGENTS.write_text(_json.dumps(_agents_payload, indent=2))
except Exception:
    # cross-ai-core too old / not installed — let the per-test fixture try.
    pass


def pytest_addoption(parser):
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="also run @pytest.mark.slow tests (subprocess / integration, no AI)",
    )
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="also run @pytest.mark.live tests (real AI calls, cache-friendly)",
    )
    parser.addoption(
        "--live-ollama",
        action="store_true",
        default=False,
        help="also run @pytest.mark.ollama tests (local Ollama daemon required)",
    )


def pytest_collection_modifyitems(config, items):
    run_slow = config.getoption("--slow")
    run_live = config.getoption("--live")
    run_ollama = config.getoption("--live-ollama")
    markexpr = getattr(config.option, "markexpr", "") or ""

    skip_slow = pytest.mark.skip(reason="slow test — run with --slow to include")
    skip_live = pytest.mark.skip(reason="live AI test — run with --live to include")
    skip_ollama = pytest.mark.skip(
        reason="Ollama live test — run with --live-ollama to include"
    )

    for item in items:
        if "slow" in item.keywords:
            if not run_slow and "slow" not in markexpr:
                item.add_marker(skip_slow)
        if "live" in item.keywords:
            if not run_live and "live" not in markexpr:
                item.add_marker(skip_live)
        if "ollama" in item.keywords:
            if not run_ollama and "ollama" not in markexpr:
                item.add_marker(skip_ollama)


def pytest_configure(config):
    """Force a headless matplotlib backend whenever --slow or --live is active.

    Several `st-*` commands (st-verdict, st-heatmap, st-plot) call
    ``matplotlib.pyplot.show()`` at the end of a successful run.  On a developer
    machine with a display, that opens a Tk/Qt/Cocoa window and the subprocess
    blocks indefinitely until a human closes the window — which causes pytest
    to hang or time out.

    Setting MPLBACKEND=Agg here (in the *parent* pytest process's environment)
    means every subprocess that does ``env = os.environ.copy()`` inherits it.
    The Agg backend has no GUI; ``plt.show()`` becomes a no-op and the
    subprocess exits cleanly.

    We do not unset it on teardown — pytest exits anyway, and unit-tier tests
    don't care about the backend.

    NOTE: st-verdict in particular renders a stacked-bar chart and starts a
    canvas timer inside ``plt.show()``'s event loop to flush AI captions.
    With Agg, the timer never fires (no event loop) but the subprocess still
    exits 0 — exactly what the live test asserts on.
    """
    import os
    if config.getoption("--slow") or config.getoption("--live"):
        os.environ.setdefault("MPLBACKEND", "Agg")


# ─────────────────────────────────────────────────────────────────────────────
# AGT-2 — session-wide agent-registry seed
# ─────────────────────────────────────────────────────────────────────────────
#
# cross-ai-core 0.8.0 stopped auto-seeding built-in providers as
# self-agents (AGT-1a).  Existing cross-st tests were written against the
# pre-0.8.0 behaviour — many call ``process_prompt("xai", …)`` or look up
# ``get_agents()["anthropic"]`` directly.
#
# Rather than rewrite every legacy test, this fixture emulates the
# Agents v2 first-run migration once at session start: it seeds one
# self-agent per built-in provider into the in-process registry so the
# legacy lookup contract still holds.
#
# Tests that explicitly want an empty registry override
# ``CROSS_AI_AGENTS_FILE`` to a fresh tmp path and call
# ``reload_agents()`` themselves — that wipes the seed for the duration
# of the test.

@pytest.fixture(autouse=True)
def _seed_legacy_agent_registry(tmp_path_factory, monkeypatch):
    """Pre-populate the agent registry with built-in self-agents.

    Mirrors the cross-ai-core test-suite's session fixture so the
    pre-0.8.0 ``--ai <make>`` / ``get_agents()[<make>]`` test patterns
    keep working without per-test setup.

    Also redirects ``CROSS_AI_AGENTS_FILE`` to a tmp path so the user's
    real ``~/.cross_ai_models.json`` (which on a developer machine has
    already been seeded with explicit models like
    ``{"anthropic": {"provider": "anthropic", "model": "claude-opus-4-5"}}``)
    cannot leak its model assignments into tests that resolve the bare
    make name and expect ``model=None`` semantics.

    Tests that override ``CROSS_AI_AGENTS_FILE`` themselves still win —
    monkeypatch later writes to env vars take precedence.
    """
    try:
        from cross_ai_core.agents import _AI_ALIASES, AgentSpec
        from cross_ai_core.ai_handler import AI_LIST
    except Exception:
        # cross-ai-core too old for the new symbols — let tests run as-is.
        yield
        return

    # Isolate from the developer's real ~/.cross_ai_models.json.
    tmp_agent_file = tmp_path_factory.mktemp("agent_seed") / "cross_ai_models.json"
    # Pre-seed the file with built-in self-agents so subprocess-based
    # tests (test_live.py, test_integration.py) inherit a populated
    # registry via the env var below — without this they see an empty
    # agents file and reject `--agent openai` with `(choose from , all)`.
    import json as _json_seed
    tmp_agent_file.write_text(_json_seed.dumps({
        "version": 2,
        "agents": {m: {"provider": m, "model": None} for m in AI_LIST},
        "_migrated_to_agents_v2": True,
    }))
    monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(tmp_agent_file))

    from collections import OrderedDict
    saved = OrderedDict(_AI_ALIASES)
    _AI_ALIASES.clear()
    for make in AI_LIST:
        _AI_ALIASES[make] = AgentSpec(make=make, model=None)
    try:
        yield
    finally:
        _AI_ALIASES.clear()
        _AI_ALIASES.update(saved)


# ─────────────────────────────────────────────────────────────────────────────
# OLL-CST-5 — Ollama daemon lifecycle fixture (@pytest.mark.ollama)
# ─────────────────────────────────────────────────────────────────────────────
#
# Ownership-aware: reuse a daemon that is already running (never tear it
# down); only start `ollama serve` ourselves when nothing is listening, and
# terminate that child on teardown.  Gated behind --live-ollama so CI stays
# daemon-free.  Uses a *tiny* model (override with CROSS_OLLAMA_TEST_MODEL)
# so a first-run `ollama pull` is cheap.

_OLLAMA_TAGS_PATH = "/api/tags"


def _ollama_base_url() -> str:
    import os
    return os.environ.get("OLLAMA_BASE_URL", "").strip() or "http://localhost:11434"


def _ollama_reachable(base_url: str, timeout: float = 2.0) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(
            base_url.rstrip("/") + _OLLAMA_TAGS_PATH, timeout=timeout
        ) as resp:
            return resp.status == 200
    except Exception:
        return False


def _stop_daemon(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    except Exception:
        pass


@pytest.fixture(scope="session")
def ollama_daemon(request):
    """Yield ``{"base_url", "model", "started"}`` for @pytest.mark.ollama tests.

    Contract:
      1. Probe ``/api/tags`` (~2 s).
      2. Reachable → **reuse**; never tear it down (ownership tracking).
      3. Not reachable + ``--live-ollama`` → ``ollama serve`` as a child, poll
         until healthy (≤30 s), ensure the tiny test model is present (pull if
         needed), terminate the child on teardown.
      4. Not runnable (no binary / never healthy / pull fails) → ``skip``.
    """
    import os
    import shutil
    import subprocess
    import time

    if not request.config.getoption("--live-ollama"):
        pytest.skip("Ollama live test — run with --live-ollama")

    base_url = _ollama_base_url()
    model = os.environ.get("CROSS_OLLAMA_TEST_MODEL", "qwen2.5:0.5b")
    proc = None
    started = False

    if not _ollama_reachable(base_url):
        if shutil.which("ollama") is None:
            pytest.skip("ollama not reachable and `ollama` binary not found")
        try:
            proc = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"could not start `ollama serve`: {exc}")
        started = True
        deadline = time.time() + 30
        while time.time() < deadline:
            if _ollama_reachable(base_url):
                break
            time.sleep(0.5)
        else:
            _stop_daemon(proc)
            pytest.skip("ollama daemon did not become healthy within 30 s")

    # Ensure the tiny test model is installed.
    try:
        from cross_ai_core.ai_ollama import OllamaHandler
        installed = OllamaHandler.list_models()
    except Exception:
        installed = []
    family = model.split(":")[0]
    have = any(t == model or t.split(":")[0] == family for t in installed)
    if not have:
        try:
            subprocess.run(["ollama", "pull", model], check=True, timeout=600)
        except Exception as exc:
            if started:
                _stop_daemon(proc)
            pytest.skip(f"could not pull test model {model!r}: {exc}")

    try:
        yield {"base_url": base_url, "model": model, "started": started}
    finally:
        if started:
            _stop_daemon(proc)



