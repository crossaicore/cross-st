"""Revisioned commands preserve array indices, history, and checker results."""
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
import _report_revisions as rr
from _revision_compat import append_fact, clear_selected_facts, guard_legacy_path, single_index


def load(name):
    spec = spec_from_file_location('revision_test_' + name.replace('-', '_'), Path(__file__).parents[1] / 'cross_st' / (name + '.py'))
    mod = module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def revision(tmp_path):
    path = tmp_path / 'report with spaces.json'
    path.write_text(json.dumps({'data': [{'prompt': 'Original intent'}], 'story': [
        {'make': 'fixture', 'model': 'old-model', 'title': 'Original', 'markdown': '# Original\n\nOld facts.', 'text': 'Old facts.', 'fact': [{'score': 4}]}]}))
    _, fp = rr.load_snapshot(path)
    rr.commit_update(path, fp, 0,
        {'make': 'fixture', 'model': 'new-model', 'title': 'Updated', 'markdown': '# Updated\n\nNew facts.', 'text': 'New facts.', 'spoken': 'New facts.'},
        {'prompt': 'assembled'}, {'id': 'p1', 'digest': 'd1', 'context': {'request': 'New intent'}}, {'method': 'interactive', 'plan_id': 'p1', 'plan_digest': 'd1'})
    return path


def test_active_selection_and_explicit_history(revision):
    container, _ = rr.load_snapshot(revision)
    assert single_index(container) == 2
    assert single_index(container, 1) == 1


def test_parallel_fact_append_keeps_history_and_binds_content(revision):
    original, _ = rr.load_snapshot(revision)
    digest = rr.content_digest(original['story'][1])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: append_fact(revision, 1, digest, {'md5_hash': str(i), 'score': i}, []), range(4)))
    result, _ = rr.load_snapshot(revision)
    assert result['story'][0] == original['story'][0]
    assert len(result['story'][1]['fact']) == 4
    assert all(f['report_id'] == result['story'][1]['report_id'] for f in result['story'][1]['fact'])
    assert all(f['content_sha256'] == digest for f in result['story'][1]['fact'])


def test_stale_fact_and_scoped_force(revision):
    before, _ = rr.load_snapshot(revision)
    with pytest.raises(ValueError, match='changed'):
        append_fact(revision, 1, 'stale', {'md5_hash': 'no'}, [])
    append_fact(revision, 1, rr.content_digest(before['story'][1]), {'md5_hash': 'yes'}, [])
    assert clear_selected_facts(revision, [1]) == 1
    after, _ = rr.load_snapshot(revision)
    assert after['story'][0]['fact'] == before['story'][0]['fact']
    assert after['story'][1]['fact'] == []


def test_unsupported_mutation_keeps_file(revision):
    original = revision.read_bytes()
    with pytest.raises(ValueError, match='does not yet support'):
        guard_legacy_path(revision, 'st-prep')
    assert revision.read_bytes() == original


def test_cat_defaults_to_active_and_renders_footer(revision, monkeypatch, capsys):
    mod = load('st-cat')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['st-cat', str(revision), '--markdown'])
    mod.main()
    text = capsys.readouterr().out
    assert 'New facts.' in text and 'Report v2 · Based on v1' in text
    assert 'Old facts.' not in text
    monkeypatch.setattr(sys, 'argv', ['st-cat', str(revision), '--markdown', '-s', '1'])
    mod.main()
    assert 'Report v1' in capsys.readouterr().out


def test_cat_current_request_not_assembled_prompt(revision, monkeypatch, capsys):
    mod = load('st-cat')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['st-cat', str(revision)])
    mod.main()
    assert capsys.readouterr().out.strip() == 'New intent'


def test_cross_dry_run_force_does_not_write_or_launch(revision, monkeypatch):
    mod = load('st-cross')
    original = revision.read_bytes()
    monkeypatch.setattr(mod.subprocess, 'run', lambda *a, **k: pytest.fail('No subprocess expected'))
    args = SimpleNamespace(story=None, dry_run=True, force=True)
    mod._cross_revisions(args, str(revision), ['checker'])
    assert revision.read_bytes() == original


def test_cross_checks_original_index_and_retains_historical_facts(revision, monkeypatch):
    mod = load('st-cross')
    calls=[]
    monkeypatch.setattr(mod, 'get_ai_make', lambda name: 'fixture')
    monkeypatch.setattr(mod, 'get_ai_model', lambda name: 'checker-model')
    monkeypatch.setattr(mod.subprocess, 'run', lambda cmd, **kw: (calls.append(cmd) or SimpleNamespace(returncode=0)))
    args = SimpleNamespace(story=None, dry_run=False, force=True, quiet=True, retry_budget=45, cache=False, timeout=0, max_concurrency=1, parallel=False)
    mod._cross_revisions(args, str(revision), ['checker'])
    assert len(calls) == 1 and calls[0][calls[0].index('-s') + 1] == '2'
    assert rr.load_snapshot(revision)[0]['story'][0]['fact'] == [{'score': 4}]


def test_revision_matrix_keeps_all_checkers(revision):
    import mmd_data_analysis as analysis
    container, _ = rr.load_snapshot(revision)
    report = container['story'][1]
    report['fact'] = [{'make': 'checker' + str(i), 'model': 'model', 'counts': [1, 0, 0, 0, 0], 'score': i} for i in range(3)]
    rows = analysis.get_flattened_fc_data(container)
    assert len(rows) == 3
    assert {r['evaluator_model'] for r in rows} == {'new-model'}


def post_module(monkeypatch, revision, on_post=None):
    mod = load('st-post')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    site = {'url': 'https://forum.invalid', 'username': 'fixture', 'api_key': 'test-key'}
    monkeypatch.setattr(mod, 'get_discourse_slugs_sites', lambda: (['test'], [site]))
    monkeypatch.setattr(mod, 'get_discourse_site', lambda *args: site)
    monkeypatch.setattr(mod, 'resolve_category', lambda *args: 1)
    captured=[]
    class Client:
        def __init__(self, *args, **kwargs): pass
        def create_post(self, body, *args, **kwargs):
            captured.append(body)
            if on_post:
                on_post()
            return {'topic_id': 7, 'topic_slug': 'report'}
    monkeypatch.setattr(mod, 'MmdDiscourseClient', Client)
    monkeypatch.setattr(sys, 'argv', ['st-post', str(revision)])
    return mod, captured


def test_post_active_footer_and_receipt_survive_concurrent_activation(revision, monkeypatch):
    before, _ = rr.load_snapshot(revision)
    mod, captured = post_module(monkeypatch, revision, lambda: rr.activate(revision, before['revisions'][0]['id']))
    mod.main()
    after, _ = rr.load_snapshot(revision)
    assert 'Report v2 · Based on v1' in captured[0]
    assert after['story'][1]['topic_id'] == 7
    assert 'topic_id' not in after['story'][0]
    assert after['active_revision_id'] == before['revisions'][0]['id']


def test_post_conflict_retains_remote_receipt(revision, monkeypatch):
    mod, captured = post_module(monkeypatch, revision)
    def fail(*args): raise ValueError('concurrent change')
    monkeypatch.setattr(mod, 'mutate_metadata', fail)
    with pytest.raises(ValueError, match='Recovery receipt'):
        mod.main()
    receipts = list((revision.parent / '.cross-receipts').glob('*.receipt'))
    assert len(captured) == 1 and len(receipts) == 1
    assert json.loads(receipts[0].read_text())['post_url'] == 'https://forum.invalid/t/report/7'


def test_post_rejects_unbound_sidecar_before_publication(revision, monkeypatch):
    mod, captured = post_module(monkeypatch, revision)
    sidecar = revision.with_suffix('.md')
    sidecar.write_text('Stale report')
    monkeypatch.setattr(sys, 'argv', ['st-post', str(revision), str(sidecar)])
    with pytest.raises(SystemExit):
        mod.main()
    assert captured == []


def test_rechecked_legacy_duplicate_gets_current_binding(revision):
    container, _ = rr.load_snapshot(revision)
    report = container['story'][0]
    def seed(current): current['story'][0]['fact'] = [{'md5_hash': 'same', 'score': 7}]
    from _revision_compat import mutate_metadata
    mutate_metadata(revision, seed)
    append_fact(revision, 0, rr.content_digest(report), {'md5_hash': 'same', 'score': 7}, [])
    facts = rr.load_snapshot(revision)[0]['story'][0]['fact']
    assert len(facts) == 1 and facts[0]['report_id'] == report['report_id']


@pytest.mark.parametrize('flag,value', [('--max-concurrency', '0'), ('--max-concurrency', '-1'), ('--timeout', '-1'), ('--retry-budget', '-1')])
def test_cross_rejects_invalid_limits_before_writes(revision, monkeypatch, flag, value):
    mod = load('st-cross')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    before = revision.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['st-cross', str(revision), '--force', flag, value])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert revision.read_bytes() == before


def test_cross_no_eligible_checkers_cannot_clear_facts(revision):
    mod = load('st-cross')
    before = revision.read_bytes()
    with pytest.raises(ValueError, match='No configured checker'):
        mod._cross_revisions(SimpleNamespace(story=None, force=True, dry_run=False), str(revision), [])
    assert revision.read_bytes() == before


def test_cross_forwards_verbose_timeout_retry_and_reports_failures(revision, monkeypatch):
    mod = load('st-cross')
    calls=[]
    monkeypatch.setattr(mod, 'get_ai_make', lambda name: 'fixture')
    monkeypatch.setattr(mod, 'get_ai_model', lambda name: 'checker-model')
    monkeypatch.setattr(mod.subprocess, 'run', lambda cmd, **kw: (calls.append((cmd, kw)) or SimpleNamespace(returncode=1)))
    args = SimpleNamespace(story=None, dry_run=False, force=False, quiet=False, verbose=True, retry_budget=9, cache=False, timeout=17, max_concurrency=1, parallel=False)
    with pytest.raises(RuntimeError, match='failed'):
        mod._cross_revisions(args, str(revision), ['checker'])
    cmd, kwargs = calls[0]
    assert '--verbose' in cmd and '--no-cache' in cmd
    assert cmd[cmd.index('--retry-budget') + 1] == '9'
    assert kwargs['timeout'] == 17


@pytest.mark.parametrize('parallel,override,expected_peak', [(True, None, 2), (True, 1, 1), (True, 2, 2), (False, 2, 1)])
def test_revision_cross_honors_parallel_and_provider_caps(revision, monkeypatch, parallel, override, expected_peak):
    import threading
    mod = load('st-cross')
    monkeypatch.setattr(mod, 'get_ai_make', lambda name: 'fixture')
    monkeypatch.setattr(mod, 'get_ai_model', lambda name: name)
    monkeypatch.setattr(mod, 'get_rate_limit_group', lambda name: ('shared-provider', 2))
    state = {'running': 0, 'peak': 0, 'calls': 0}
    lock = threading.Lock()
    rendezvous = threading.Barrier(2)
    def run(cmd, **kwargs):
        with lock:
            state['running'] += 1
            state['calls'] += 1
            state['peak'] = max(state['peak'], state['running'])
        if expected_peak == 2:
            rendezvous.wait(timeout=2)
        else:
            threading.Event().wait(0.03)
        with lock:
            state['running'] -= 1
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, 'run', run)
    args = SimpleNamespace(story=None, dry_run=False, force=False, quiet=True, verbose=False, retry_budget=9, cache=True, timeout=0, max_concurrency=override, parallel=parallel)
    mod._cross_revisions(args, str(revision), ['checker-one', 'checker-two'])
    assert state['calls'] == 2 and state['peak'] == expected_peak
