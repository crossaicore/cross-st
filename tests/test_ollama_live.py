"""
tests/test_ollama_live.py — OLL-CST-5 live integration tests.

Opt-in (``@pytest.mark.ollama``); skipped unless ``--live-ollama`` is passed
AND a local Ollama daemon is reachable (or startable).  The ``ollama_daemon``
session fixture (tests/conftest.py) handles the daemon lifecycle and ensures a
tiny model (``CROSS_OLLAMA_TEST_MODEL``, default ``qwen2.5:0.5b``) is present.

Run:  pytest tests/test_ollama_live.py --live-ollama

Covers, against a real daemon:
  * connectivity + discovery helpers (health_check / list_models)
  * st-admin's ``_agent_admin.get_ollama_models()`` picker source
  * one end-to-end ``process_prompt("ollama-<model>", …)`` through the cross-st
    ``ai_handler`` shim
  * the OLL-CST-3 keyless-filtering guards with a real Ollama agent
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.ollama

_CROSS_ST = str(Path(__file__).parent.parent / "cross_st")
if _CROSS_ST not in sys.path:
    sys.path.insert(0, _CROSS_ST)


# ── Connectivity / discovery ──────────────────────────────────────────────────

class TestLiveDiscovery:
    def test_health_check_true(self, ollama_daemon):
        from cross_ai_core.ai_ollama import OllamaHandler
        assert OllamaHandler.health_check() is True

    def test_list_models_has_test_model(self, ollama_daemon):
        from cross_ai_core.ai_ollama import OllamaHandler
        family = ollama_daemon["model"].split(":")[0]
        tags = OllamaHandler.list_models()
        assert any(t.split(":")[0] == family for t in tags), tags

    def test_st_admin_discovery_source(self, ollama_daemon):
        import _agent_admin
        models = _agent_admin.get_ollama_models()
        assert models  # non-empty — the wizard picker would list these


# ── End-to-end generation through the cross-st shim ───────────────────────────

class TestLiveGeneration:
    def test_process_prompt_e2e(self, ollama_daemon, tmp_path, monkeypatch):
        # Define an ollama agent bound to the tiny test model.
        agent_file = tmp_path / "cross_ai_models.json"
        agent_file.write_text(json.dumps({
            "ollama-test": {"make": "ollama", "model": ollama_daemon["model"]},
        }))
        monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(agent_file))
        from cross_ai_core.agents import reload_agents
        reload_agents()
        try:
            # Through the cross-st ai_handler shim (re-exports cross-ai-core).
            from ai_handler import process_prompt, get_content_auto
            result = process_prompt(
                "ollama-test",
                "Reply with exactly one word: pong",
                use_cache=False,
            )
            text = get_content_auto(result.response)
            assert isinstance(text, str) and text.strip()
            assert result.response["_make"] == "ollama"
        finally:
            monkeypatch.delenv("CROSS_AI_AGENTS_FILE", raising=False)
            reload_agents()


# ── Keyless filtering with a real ollama agent (OLL-CST-3, live) ──────────────

class TestLiveKeylessFiltering:
    def test_ollama_agent_survives_key_filter(self, ollama_daemon, tmp_path, monkeypatch):
        agent_file = tmp_path / "cross_ai_models.json"
        agent_file.write_text(json.dumps({
            "ollama-test": {"make": "ollama", "model": ollama_daemon["model"]},
            "xai":         {"make": "xai",    "model": None},
        }))
        monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(agent_file))
        from cross_ai_core.keys import PROVIDER_API_KEY_ENV
        for env_names in PROVIDER_API_KEY_ENV.values():
            for var in env_names:
                monkeypatch.delenv(var, raising=False)
        from cross_ai_core.agents import reload_agents
        reload_agents()
        try:
            import _agent_admin
            kept = {r["agent"] for r in _agent_admin.list_agents(filter_by_keys=True)}
            assert "ollama-test" in kept   # keyless → always available
            assert "xai" not in kept       # keyed, no key → dropped
        finally:
            monkeypatch.delenv("CROSS_AI_AGENTS_FILE", raising=False)
            reload_agents()

