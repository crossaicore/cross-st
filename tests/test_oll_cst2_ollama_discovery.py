"""
tests/test_oll_cst2_ollama_discovery.py — OLL-CST-2 regression tests.

Wire live Ollama model discovery into the st-admin agent wizard:

  * ``_agent_admin.get_ollama_models()``  — live /api/tags wrapper (OLL-3
    OllamaHandler.list_models), [] on failure.
  * ``st-admin._pick_model("ollama")``    — lists discovered tags, honours
    numeric / free-text / default(0) choices; ollama-specific empty-state hint.
  * Non-interactive parity: ``add_agent(name, "ollama", model)`` persists a
    ``{provider: "ollama", model: …}`` spec (backs ``--add-agent`` CLI).
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
from cross_ai_core.ai_ollama import OllamaHandler  # noqa: E402

# st-admin.py has a hyphen → load via importlib.
_SPEC = importlib.util.spec_from_file_location(
    "st_admin_oll", Path(_CROSS_ST) / "st-admin.py"
)
st_admin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(st_admin)


@pytest.fixture
def isolated_agents(tmp_path, monkeypatch):
    f = tmp_path / "cross_ai_models.json"
    monkeypatch.setenv("CROSS_AI_AGENTS_FILE", str(f))
    reload_agents()
    yield f
    monkeypatch.delenv("CROSS_AI_AGENTS_FILE", raising=False)
    reload_agents()


# ── get_ollama_models ─────────────────────────────────────────────────────────

class TestGetOllamaModels:
    def test_returns_tags(self, monkeypatch):
        monkeypatch.setattr(
            OllamaHandler, "list_models",
            staticmethod(lambda: ["llama3.1:latest", "mistral:latest"]),
        )
        assert _agent_admin.get_ollama_models() == ["llama3.1:latest", "mistral:latest"]

    def test_empty_on_error(self, monkeypatch):
        def boom():
            raise RuntimeError("daemon down")
        monkeypatch.setattr(OllamaHandler, "list_models", staticmethod(boom))
        assert _agent_admin.get_ollama_models() == []


# ── _pick_model("ollama") ─────────────────────────────────────────────────────

class TestPickModelOllama:
    def test_picks_discovered_by_number(self, monkeypatch):
        monkeypatch.setattr(
            _agent_admin, "get_ollama_models",
            lambda: ["llama3.1:latest", "mistral:latest"],
        )
        monkeypatch.setattr("builtins.input", lambda *a, **k: "2")
        confirmed, model = st_admin._pick_model("ollama")
        assert confirmed is True
        assert model == "mistral:latest"

    def test_free_text_when_not_installed(self, monkeypatch):
        monkeypatch.setattr(_agent_admin, "get_ollama_models", lambda: [])
        monkeypatch.setattr("builtins.input", lambda *a, **k: "qwen2.5:0.5b")
        confirmed, model = st_admin._pick_model("ollama")
        assert confirmed is True
        assert model == "qwen2.5:0.5b"

    def test_zero_selects_default(self, monkeypatch):
        monkeypatch.setattr(_agent_admin, "get_ollama_models", lambda: ["llama3.1:latest"])
        monkeypatch.setattr("builtins.input", lambda *a, **k: "0")
        confirmed, model = st_admin._pick_model("ollama")
        assert confirmed is True
        assert model is None

    def test_empty_state_hint_shown(self, monkeypatch, capsys):
        monkeypatch.setattr(_agent_admin, "get_ollama_models", lambda: [])
        monkeypatch.setattr("builtins.input", lambda *a, **k: "")
        confirmed, model = st_admin._pick_model("ollama")
        assert confirmed is False
        out = capsys.readouterr().out
        assert "ollama pull" in out
        assert "11434" in out  # the OLLAMA_BASE_URL appears in the hint


# ── Non-interactive parity: add_agent for ollama ──────────────────────────────

class TestAddOllamaAgent:
    def test_add_agent_persists_ollama_spec(self, isolated_agents):
        _agent_admin.add_agent("ollama-llama", "ollama", "llama3.1")
        data = _agent_admin.read_agents_file()
        assert data["ollama-llama"] == {"make": "ollama", "model": "llama3.1"}
        # And the on-disk envelope stores it as provider/model (v2 shape).
        env = json.loads(isolated_agents.read_text())
        assert env["agents"]["ollama-llama"] == {"provider": "ollama", "model": "llama3.1"}

    def test_add_agent_model_optional(self, isolated_agents):
        _agent_admin.add_agent("ollama-default", "ollama", None)
        assert _agent_admin.read_agents_file()["ollama-default"] == {
            "make": "ollama", "model": None,
        }

