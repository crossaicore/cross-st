"""Focused tests for st-new's optional spell-check integration."""

import runpy
from pathlib import Path


_ROOT = Path(__file__).parent.parent


def _load_st_new():
    return runpy.run_path(str(_ROOT / "cross_st" / "st-new.py"), run_name="st_new_test")


def test_spell_check_is_skipped_when_aspell_is_missing(monkeypatch, capsys):
    module = _load_st_new()
    monkeypatch.setattr(module["shutil"], "which", lambda name: None)

    module["run_spell_check"]("example.prompt")

    assert "Spell check skipped" in capsys.readouterr().out