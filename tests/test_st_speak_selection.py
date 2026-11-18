"""Speech CLI and menu use the same one-based report indices as st-ls."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).parents[1]


def load_command(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_') + '_selection_test',
                                                  ROOT / 'cross_st' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def speak(monkeypatch):
    module = load_command('st-speak')
    monkeypatch.setattr(module, 'require_config', lambda: None)
    monkeypatch.setattr(module, 'load_cross_env', lambda: None)
    monkeypatch.setattr(module, 'render_audio', Mock(return_value=True))
    return module


@pytest.mark.parametrize('count,flags,selected', [
    (1, [], 1), (2, [], 1), (2, ['-s', '1'], 1),
    (2, ['-s', '2'], 2), (6, ['-s', '6'], 6),
])
def test_renders_selected_report_without_changing_container(speak, monkeypatch, tmp_path, count, flags, selected):
    path = tmp_path / 'spoken challenge.json'
    # Raw positions/counts are intentionally unrelated to prepared report indices.
    path.write_text(json.dumps({'data': [], 'story': [
        {'spoken': f'Saved speech for report {i}.', 'fact': [],
         '_generated_by': 'st-update' if i > 1 else 'st-gen'}
        for i in range(1, count + 1)]}))
    before = path.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['st-speak', *flags, str(path)])
    speak.main()
    speak.render_audio.assert_called_once_with(
        f'Saved speech for report {selected}.', str(path.with_suffix('.mp3')),
        None, quiet=False, verbose=False)
    assert path.read_bytes() == before
    assert not path.with_suffix('.mp3').exists()  # renderer is mocked


@pytest.mark.parametrize('count,index', [(2, 0), (2, -1), (2, 3), (0, 1)])
def test_invalid_index_fails_before_rendering(speak, monkeypatch, tmp_path, capsys, count, index):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'story': [{'spoken': 'Body'}] * count}))
    monkeypatch.setattr(sys, 'argv', ['st-speak', '-s', str(index), str(path)])
    with pytest.raises(SystemExit) as result:
        speak.main()
    assert result.value.code == 1
    speak.render_audio.assert_not_called()
    message = capsys.readouterr().out
    assert f'Report index out of range: {index}' in message
    assert 'st-ls' in message
    assert 'list index' not in message


@pytest.mark.parametrize('spoken', [None, '', '  '])
def test_empty_speech_is_reported_before_rendering(speak, monkeypatch, tmp_path, capsys, spoken):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'story': [{'spoken': spoken}]}))
    monkeypatch.setattr(sys, 'argv', ['st-speak', str(path)])
    with pytest.raises(SystemExit) as result:
        speak.main()
    assert result.value.code == 1
    speak.render_audio.assert_not_called()
    assert 'Report 1 has no spoken text' in capsys.readouterr().out


def test_unsuccessful_render_has_failure_exit_status(speak, monkeypatch, tmp_path):
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'story': [{'spoken': 'Body'}]}))
    monkeypatch.setattr(sys, 'argv', ['st-speak', str(path)])
    speak.render_audio.return_value = False
    with pytest.raises(SystemExit) as result:
        speak.main()
    assert result.value.code == 1
    speak.render_audio.assert_called_once()


@pytest.mark.parametrize('choice,render_status,play', [
    ('v', 0, True), ('V', 0, False), ('v', 1, False), ('V', 1, False),
])
def test_utility_actions_keep_report_index_and_file_path(monkeypatch, tmp_path, choice, render_status, play):
    import discourse
    import mmd_startup
    monkeypatch.setattr(discourse, 'get_discourse_slugs_sites', lambda: ([], []))
    monkeypatch.setattr(mmd_startup, 'load_cross_env', lambda: None)
    menu = load_command('st')
    path = tmp_path / 'spoken challenge.json'
    menu.file_json = str(path)
    menu.file_prefix = str(path.with_suffix(''))
    menu.story_sel = 2
    calls = []
    def run(command):
        calls.append(command)
        return SimpleNamespace(returncode=render_status)
    monkeypatch.setattr(menu.subprocess, 'run', run)
    menu.execute_menu('Utility', choice)
    expected = [['st-speak', '-s', '2', str(path)]]
    if play:
        expected.append(['afplay', str(path.with_suffix('.mp3'))])
    assert calls == expected
