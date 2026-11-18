"""Fix/merge create successors while retaining historical reports and facts."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import _report_revisions as rr


def load(name):
    spec = spec_from_file_location('successor_test_' + name.replace('-', '_'), Path(__file__).parents[1] / 'cross_st' / (name + '.py'))
    mod = module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def revision(tmp_path):
    path = tmp_path / 'report with spaces.json'
    path.write_text(json.dumps({'data': [{'prompt': 'Original intent'}], 'story': [
        {'make': 'fixture', 'model': 'old', 'title': 'Original', 'markdown': '# Original\n\nOld facts.', 'text': 'Old facts.', 'fact': [{'score': 4}]}]}))
    _, fp = rr.load_snapshot(path)
    rr.commit_update(path, fp, 0,
        {'make': 'fixture', 'model': 'new', 'title': 'Updated', 'markdown': '# Updated\n\nNew facts.', 'text': 'New facts.', 'spoken': 'STALE SPEECH'},
        {'prompt': 'assembled'}, {'id': 'p1', 'digest': 'd1', 'context': {'request': 'New intent'}}, {'method': 'interactive', 'plan_id': 'p1', 'plan_digest': 'd1'})
    return path


def test_fix_save_creates_successor_without_stale_derived_fields(revision):
    mod = load('st-fix')
    before, fingerprint = rr.load_snapshot(revision)
    args = SimpleNamespace(agent='fixture', mode='patch', story=2, fact=1, quiet=True,
                           prep=True, verbose=False, cache=True, _revision_fingerprint=fingerprint)
    mod._save_result(before, str(revision), args, 'fixture', 'old', 'new',
                     '# Updated\n\nCorrected facts.', {}, '', before['story'][1], skip_after_factcheck=True)
    after, _ = rr.load_snapshot(revision)
    assert after['story'][:2] == before['story']
    child = after['story'][2]
    assert child['fact'] == []
    assert 'STALE SPEECH' not in child['spoken']
    assert 'Corrected facts' in child['spoken']
    assert child['source_data_id'] == after['data'][-1]['data_id']
    assert after['revisions'][-1]['kind'] == 'fix'
    assert after['revisions'][-1]['parent_report_ids'] == [before['story'][1]['report_id']]
    assert 'approved_plan' not in after['revisions'][-1]


def test_fix_rejects_unsupported_modes_before_ai(revision, monkeypatch):
    mod = load('st-fix')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    monkeypatch.setattr(mod, 'get_ai_list', lambda: ['fixture'])
    monkeypatch.setattr(mod, 'get_default_ai', lambda: 'fixture')
    monkeypatch.setattr(mod, 'process_prompt', lambda *_args, **_kwargs: pytest.fail('No AI expected'))
    monkeypatch.setattr(sys, 'argv', ['st-fix', str(revision), '--mode', 'synthesize'])
    before = revision.read_bytes()
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert revision.read_bytes() == before


def setup_merge(monkeypatch):
    mod = load('st-merge')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    monkeypatch.setattr(mod, 'get_ai_list', lambda: ['fixture'])
    monkeypatch.setattr(mod, 'get_default_ai', lambda: 'fixture')
    monkeypatch.setattr(mod, 'get_ai_model', lambda _: 'new')
    monkeypatch.setattr(mod, 'get_ai_make_model', lambda _: 'fixture:new')
    monkeypatch.setattr(mod, 'get_content_auto', lambda _: '# Merged\n\nCombined facts.')
    return mod


def test_merge_single_active_needs_explicit_history(revision, monkeypatch):
    mod = setup_merge(monkeypatch)
    monkeypatch.setattr(mod, 'process_prompt', lambda *_args, **_kwargs: pytest.fail('No AI expected'))
    monkeypatch.setattr(sys, 'argv', ['st-merge', str(revision), '--simple'])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2


def test_merge_historical_selection_tracks_all_parents(revision, monkeypatch):
    mod = setup_merge(monkeypatch)
    before, _ = rr.load_snapshot(revision)
    calls = []
    def generate(*args, **kwargs):
        calls.append((args, kwargs))
        return {}, None, {}, 'new'
    monkeypatch.setattr(mod, 'process_prompt', generate)
    monkeypatch.setattr(sys, 'argv', ['st-merge', str(revision), '--stories', '1', '2', '--simple', '--no-post-check', '-q'])
    mod.main()
    after, _ = rr.load_snapshot(revision)
    assert after['story'][:2] == before['story']
    assert len(after['story']) == 3
    assert len(after['data']) == len(before['data']) + 1
    revision_record = after['revisions'][-1]
    assert revision_record['kind'] == 'merge'
    assert revision_record['parent_report_ids'] == [r['report_id'] for r in before['story']]
    assert 'approved_plan' not in revision_record
    assert after['story'][-1]['fact'] == []
    assert 'Report v3' in rr.render_report(after['story'][-1])
    assert len(calls) == 1


def test_merge_rejects_unselected_base_before_call(revision, monkeypatch):
    mod = setup_merge(monkeypatch)
    monkeypatch.setattr(mod, 'process_prompt', lambda *_args, **_kwargs: pytest.fail('No AI expected'))
    monkeypatch.setattr(sys, 'argv', ['st-merge', str(revision), '--stories', '1', '2', '--base', '3', '--simple', '--no-post-check'])
    with pytest.raises(SystemExit):
        mod.main()


def test_fix_concurrent_change_preserves_recovery(revision, tmp_path):
    mod = load('st-fix')
    before, fingerprint = rr.load_snapshot(revision)
    args = SimpleNamespace(agent='fixture', mode='patch', story=2, fact=1, quiet=True,
                           prep=True, verbose=False, cache=True, _revision_fingerprint=fingerprint)
    rr.activate(revision, before['revisions'][0]['id'])
    changed = revision.read_bytes()
    with pytest.raises(ValueError, match='retained at'):
        mod._save_result(before, str(revision), args, 'fixture', 'old', 'new',
                         '# Updated\n\nCorrected facts.', {}, '', before['story'][1])
    assert revision.read_bytes() == changed
    assert list((tmp_path / '.cross-update').glob('fix-*.attempt'))


def test_fix_auto_selection_uses_active_report_and_original_index(revision, monkeypatch, capsys):
    mod = load('st-fix')
    container, fingerprint = rr.load_snapshot(revision)
    for report in container['story']:
        report['fact'] = [{'make': 'fixture', 'model': 'checker', 'score': 1.0,
                          'counts': [0, 0, 0, 0, 1],
                          'report': 'Claim 1: "New facts."\nVerification: False\nExplanation: Supplied correction.\n'}]
    rr.atomic_write(revision, container, fingerprint)
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    monkeypatch.setattr(mod, 'get_ai_list', lambda: ['fixture'])
    monkeypatch.setattr(mod, 'get_default_ai', lambda: 'fixture')
    monkeypatch.setattr(mod, 'process_prompt', lambda *_args, **_kwargs: pytest.fail('No AI expected'))
    monkeypatch.setattr(sys, 'argv', ['st-fix', str(revision), '--mode', 'patch', '--dry-run'])
    mod.main()
    text = capsys.readouterr().out
    assert 'Auto-selected: story 2' in text
    assert 'Auto-selected: story 1' not in text
    monkeypatch.setattr(sys, 'argv', ['st-fix', str(revision), '--mode', 'patch', '--dry-run', '-s', '1', '-f', '1'])
    mod.main()
    assert 'Story 1' in capsys.readouterr().out
