"""
tests/test_oll_cst3_keyless.py — OLL-CST-3 regression tests.

Ollama is the first **keyless** provider (local/LAN; absent from
``cross_ai_core.PROVIDER_API_KEY_ENV``).  These tests lock the "always
available" behaviour across the four AGT-5 key-filtered surfaces so an
Ollama agent is never dropped and never crashes a caller:

  1. ``_agent_admin.list_agents(filter_by_keys=True)`` / ``_has_api_key_safe``
  2. ``_agent_admin.agents_missing_keys`` (st-admin> AI> M hints)
  3. ``st.py`` ``_agents_with_keys`` rotation filter
  4. ``st-cross`` ``_filter_agents_by_key`` matrix column filter

Regression guard: before OLL-CST-3, ``st-cross`` called ``has_api_key('ollama')``
which raises ``ValueError`` — only ``ImportError`` was caught, so it crashed.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_CROSS_ST = str(Path(__file__).parent.parent / "cross_st")
if _CROSS_ST not in sys.path:
    sys.path.insert(0, _CROSS_ST)

import _agent_admin  # noqa: E402
from cross_ai_core.agents import reload_agents  # noqa: E402
from cross_ai_core.keys import PROVIDER_API_KEY_ENV  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def keyless_registry(tmp_path, monkeypatch):
    """Seed an agent file with one keyless (ollama) + one keyed (xai) agent,
    with every provider API key stripped from the env."""
    f = tmp_path / "cross_ai_models.json"
    f.write_text(json.dumps({
        "ollama": {"make": "ollama", "model": "llama3.1"},
        "xai":    {"make": "xai",    "model": None},
    }))
    monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(f))
    for env_names in PROVIDER_API_KEY_ENV.values():
        for var in env_names:
            monkeypatch.delenv(var, raising=False)
    reload_agents()
    yield f
    monkeypatch.delenv("CROSS_AI_AGENTS_FILE", raising=False)
    reload_agents()


def _load_module(name: str, filename: str):
    path = Path(_CROSS_ST) / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 1. _agent_admin predicates + list_agents ──────────────────────────────────

class TestKeylessPredicate:
    def test_ollama_does_not_need_key(self):
        assert _agent_admin._provider_needs_key("ollama") is False

    def test_cloud_makes_need_key(self):
        for make in PROVIDER_API_KEY_ENV:
            assert _agent_admin._provider_needs_key(make) is True

    def test_ollama_always_available(self, monkeypatch):
        for env_names in PROVIDER_API_KEY_ENV.values():
            for var in env_names:
                monkeypatch.delenv(var, raising=False)
        assert _agent_admin._has_api_key_safe("ollama") is True

    def test_keyed_make_reflects_env(self, monkeypatch):
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        assert _agent_admin._has_api_key_safe("xai") is False
        monkeypatch.setenv("XAI_API_KEY", "x-test")
        assert _agent_admin._has_api_key_safe("xai") is True


class TestListAgentsKeyless:
    def test_ollama_kept_when_filtering_and_no_keys(self, keyless_registry):
        rows = _agent_admin.list_agents(filter_by_keys=True)
        agents = {r["agent"] for r in rows}
        assert "ollama" in agents      # keyless → survives
        assert "xai" not in agents     # keyed, no key → dropped

    def test_agents_missing_keys_excludes_ollama(self, keyless_registry):
        missing = {make for _a, make, _e in _agent_admin.agents_missing_keys()}
        assert "ollama" not in missing
        assert "xai" in missing        # keyed + no key → reported


# ── 3. st.py rotation filter ──────────────────────────────────────────────────

class TestStPyRotation:
    def test_ollama_in_rotation_without_keys(self, keyless_registry):
        st = _load_module("st_keyless_ut", "st.py")
        rotation = st._agents_with_keys()
        assert "ollama" in rotation
        # Module-level ai_opt (computed at import) also includes it.
        assert "ollama" in st.ai_opt


# ── 4. st-cross matrix filter (regression: used to crash on ollama) ───────────

class TestStCrossFilter:
    def test_ollama_kept_and_no_crash_without_keys(self, keyless_registry):
        stx = _load_module("st_cross_keyless_ut", "st-cross.py")
        kept, dropped = stx._filter_agents_by_key(["ollama", "xai"])
        assert "ollama" in kept                       # keyless survives
        assert "xai" not in kept                       # keyed, no key → dropped
        assert ("xai", "xai", "XAI_API_KEY") in dropped
        assert all(name != "ollama" for name, _m, _e in dropped)

    def test_keyed_agent_kept_when_key_present(self, keyless_registry, monkeypatch):
        monkeypatch.setenv("XAI_API_KEY", "x-test")
        stx = _load_module("st_cross_keyed_ut", "st-cross.py")
        kept, dropped = stx._filter_agents_by_key(["ollama", "xai"])
        assert set(kept) == {"ollama", "xai"}
        assert dropped == []

