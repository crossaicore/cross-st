"""
tests/test_oll_cst4_parallel.py — OLL-CST-4 regression tests.

Verify `st-cross --parallel` treats multiple Ollama agents correctly:

  * two ollama agents share ONE semaphore (rate-limit group = resolved make
    "ollama"), so they don't over-subscribe local hardware;
  * the semaphore size is the OLL-4 cap (get_rate_limit_concurrency("ollama")
    = 2 by default, tunable via OLLAMA_MAX_CONCURRENCY);
  * an ollama group is distinct from a cloud provider's group;
  * --sequential collapses everything to one shared semaphore;
  * ollama agents are never dropped from the matrix column list (keyless).

These are deterministic (no daemon needed) — a full live parallel matrix run
is exercised manually via the OLL-CST-5 `--live-ollama` fixture + a real report.
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


@pytest.fixture
def st_cross_mod():
    path = Path(_CROSS_ST) / "st-cross.py"
    spec = importlib.util.spec_from_file_location("st_cross_oll4", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def _reset_semaphores(st_cross_mod):
    st_cross_mod._provider_semaphores.clear()
    yield
    st_cross_mod._provider_semaphores.clear()


@pytest.fixture
def ollama_agents(tmp_path, monkeypatch):
    """Two ollama agents (different models) + one cloud agent."""
    path = tmp_path / "cross_ai_models.json"
    path.write_text(json.dumps({
        "ollama-llama":   {"make": "ollama", "model": "llama3.1"},
        "ollama-mistral": {"make": "ollama", "model": "mistral"},
        "xai":            {"make": "xai",    "model": None},
    }))
    monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(path))
    from cross_ai_core.agents import reload_agents
    reload_agents()
    yield path
    monkeypatch.delenv("CROSS_AI_AGENTS_FILE", raising=False)
    reload_agents()


# ── Rate-limit group / semaphore sharing ──────────────────────────────────────

class TestOllamaSemaphoreGroup:
    def test_two_ollama_agents_share_semaphore(
            self, st_cross_mod, _reset_semaphores, ollama_agents):
        a = st_cross_mod._get_provider_semaphore("ollama-llama", None, sequential=False)
        b = st_cross_mod._get_provider_semaphore("ollama-mistral", None, sequential=False)
        assert a is b  # same "ollama" rate-limit group → one semaphore

    def test_ollama_distinct_from_cloud(
            self, st_cross_mod, _reset_semaphores, ollama_agents):
        oll = st_cross_mod._get_provider_semaphore("ollama-llama", None, sequential=False)
        xai = st_cross_mod._get_provider_semaphore("xai", None, sequential=False)
        assert oll is not xai

    def test_group_key_is_ollama(self, ollama_agents):
        from cross_ai_core import get_rate_limit_group
        group, cap = get_rate_limit_group("ollama-mistral")
        assert group == "ollama"
        assert cap == 2  # OLL-4 default


# ── Concurrency cap (OLL-4) applied to the semaphore ──────────────────────────

class TestOllamaSemaphoreSize:
    def test_default_cap_is_two(
            self, st_cross_mod, _reset_semaphores, ollama_agents, monkeypatch):
        monkeypatch.delenv("OLLAMA_MAX_CONCURRENCY", raising=False)
        sem = st_cross_mod._get_provider_semaphore("ollama-llama", None, sequential=False)
        assert sem.acquire(blocking=False) is True   # 1
        assert sem.acquire(blocking=False) is True   # 2
        assert sem.acquire(blocking=False) is False  # cap = 2 exhausted

    def test_env_override_changes_cap(
            self, st_cross_mod, _reset_semaphores, ollama_agents, monkeypatch):
        monkeypatch.setenv("OLLAMA_MAX_CONCURRENCY", "1")
        sem = st_cross_mod._get_provider_semaphore("ollama-llama", None, sequential=False)
        assert sem.acquire(blocking=False) is True    # 1
        assert sem.acquire(blocking=False) is False   # cap = 1

    def test_max_override_flag_wins(
            self, st_cross_mod, _reset_semaphores, ollama_agents):
        # --max-concurrency 3 overrides the group cap for ollama too.
        sem = st_cross_mod._get_provider_semaphore("ollama-llama", 3, sequential=False)
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is False   # cap = 3


# ── Sequential fallback ───────────────────────────────────────────────────────

class TestSequential:
    def test_sequential_shares_one_semaphore(
            self, st_cross_mod, _reset_semaphores, ollama_agents):
        a = st_cross_mod._get_provider_semaphore("ollama-llama", None, sequential=True)
        b = st_cross_mod._get_provider_semaphore("xai", None, sequential=True)
        assert a is b is st_cross_mod._sequential_semaphore


# ── Matrix column list keeps ollama agents (keyless) ──────────────────────────

class TestMatrixColumns:
    def test_ollama_agents_kept_without_keys(
            self, st_cross_mod, ollama_agents, monkeypatch):
        from cross_ai_core.keys import PROVIDER_API_KEY_ENV
        for env_names in PROVIDER_API_KEY_ENV.values():
            for var in env_names:
                monkeypatch.delenv(var, raising=False)
        kept, dropped = st_cross_mod._filter_agents_by_key(
            ["ollama-llama", "ollama-mistral", "xai"]
        )
        assert "ollama-llama" in kept and "ollama-mistral" in kept
        assert "xai" not in kept  # keyed, no key → dropped column

