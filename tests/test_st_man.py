"""Manual discovery must include every packaged command without importing it."""
import importlib.util
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def manual():
    spec = importlib.util.spec_from_file_location('st_man_test', ROOT / 'cross_st/st-man.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_includes_every_entry_point(manual):
    scripts = (ROOT / 'pyproject.toml').read_text().split('[project.scripts]', 1)[1].split('\n[', 1)[0]
    commands = set(re.findall(r'^(st(?:-[\w-]+)?)\s*=', scripts, re.M))
    assert set(manual.COMMANDS) == commands
    assert manual.COMMANDS[0] == 'st'


@pytest.mark.parametrize('name', ['st-update', 'update'])
def test_update_help_is_available(manual, monkeypatch, capsys, name):
    monkeypatch.setattr(sys, 'argv', ['st-man', name])
    manual.main()
    output = capsys.readouterr().out
    assert 'Update a selected report, then review the saved result' in output
    assert '--update-details' in output
    assert 'https://github.com/crossaicore/cross-st/wiki/st-update' in output
    assert 'Unknown command' not in output


def test_index_includes_new_commands(manual, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['st-man'])
    manual.main()
    output = capsys.readouterr().out
    assert 'st-update' in output and 'st-ask' in output and 'st-pdf' in output


def test_pdf_manual_is_available(manual, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['st-man', 'st-pdf'])
    manual.main()
    output = capsys.readouterr().out
    assert 'Export reports as PDF' in output
    assert '--output' in output and 'Maker Matt Design' in output
    assert 'https://github.com/crossaicore/cross-st/wiki/st-pdf' in output


def test_unknown_command_still_rejected(manual, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['st-man', 'not-a-command'])
    with pytest.raises(SystemExit) as error:
        manual.main()
    assert error.value.code == 1


def test_web_help_uses_canonical_wiki(manual, monkeypatch):
    opened = []
    monkeypatch.setattr(manual.webbrowser, 'open', opened.append)
    monkeypatch.setattr(sys, 'argv', ['st-man', 'update', '--web'])
    manual.main()
    assert opened == ['https://github.com/crossaicore/cross-st/wiki/st-update']
