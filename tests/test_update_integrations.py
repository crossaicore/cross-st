"""Ordinary editing/publication/checking remains content-bound after updates."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from _report_content import content_identity, edited_report, save_fact, save_publication
from _report_store import ConcurrentWriteError, load_snapshot

ROOT = Path(__file__).parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'cross_st' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def report_file(tmp_path):
    data = []
    reports = []
    for n in range(1, 7):
        data.append({'data_id': str(n), 'markdown': f'Raw {n}', 'gen_response': {'json': 'raw provider data'}, 'update_request': 'Extend report' if n == 6 else ''})
        reports.append({'source_data_id': str(n), 'make': 'agent', 'model': 'model', 'title': f'Report {n}', 'markdown': f'# Report {n}\n\nSaved **body {n}**.', 'text': f'Saved body {n}.', 'spoken': f'Spoken {n}', 'fact': [{'md5_hash': 'old'}], 'segments': [{'text': f'Saved body {n}.'}]})
    path = tmp_path / 'report.json'
    path.write_text(json.dumps({'data': data, 'story': reports}))
    return path


def read(path):
    return json.loads(path.read_text())


def test_edit_markdown_in_place_rebuilds_and_preserves_raw(report_file, monkeypatch):
    mod = module('st-edit')
    original = read(report_file)
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    def edit(cmd, **kwargs):
        assert cmd[:2] == ['fake-editor', '--wait']
        Path(cmd[-1]).write_text('# Human heading\n\nHuman **table** edits. #report')
        return SimpleNamespace(returncode=0)
    monkeypatch.setenv('EDITOR', 'fake-editor --wait')
    monkeypatch.setattr(mod.subprocess, 'run', edit)
    monkeypatch.setattr(sys, 'argv', ['st-edit', '--markdown', '-s', '6', str(report_file)])
    mod.main()
    saved = read(report_file)
    assert len(saved['story']) == 6
    assert saved['story'][:5] == original['story'][:5]
    assert saved['data'] == original['data']
    report = saved['story'][5]
    assert 'Human table edits.' in report['text']
    assert 'Human' in report['spoken']
    assert report['fact'] == [] and 'segments' not in report
    assert report['source_data_id'] == '6'
    assert report['markdown'].startswith('# Human heading')


def test_edit_failed_editor_does_not_save(report_file, monkeypatch):
    mod = module('st-edit')
    before = report_file.read_bytes()
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    def fail(cmd, **kwargs):
        Path(cmd[-1]).write_text('Incomplete edit')
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(mod.subprocess, 'run', fail)
    monkeypatch.setattr(sys, 'argv', ['st-edit', '--markdown', str(report_file)])
    with pytest.raises(SystemExit):
        mod.main()
    assert report_file.read_bytes() == before


def test_edit_detects_concurrent_replacement(report_file, monkeypatch):
    mod = module('st-edit')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    def concurrent(cmd, **kwargs):
        current = read(report_file)
        current['story'][0]['markdown'] = 'Concurrent update'
        report_file.write_text(json.dumps(current))
        Path(cmd[-1]).write_text('My edit')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, 'run', concurrent)
    monkeypatch.setattr(sys, 'argv', ['st-edit', '--markdown', str(report_file)])
    with pytest.raises(SystemExit):
        mod.main()
    assert read(report_file)['story'][0]['markdown'] == 'Concurrent update'


def test_content_check_merge_and_replacement_refusal(report_file):
    report = read(report_file)['story'][5]
    identity = content_identity(report)
    save_fact(report_file, 5, identity, {'md5_hash': 'new1'}, report['segments'])
    save_fact(report_file, 5, identity, {'md5_hash': 'new2'}, report['segments'])
    assert len(read(report_file)['story'][5]['fact']) == 3
    changed = read(report_file)
    changed['story'][5]['markdown'] = 'Iterated content'
    report_file.write_text(json.dumps(changed))
    before = report_file.read_bytes()
    with pytest.raises(ConcurrentWriteError):
        save_fact(report_file, 5, identity, {'md5_hash': 'stale'}, report['segments'])
    assert report_file.read_bytes() == before


def post_setup(monkeypatch, calls, callback=None):
    mod = module('st-post')
    site = {'url': 'https://forum.example', 'username': 'test', 'api_key': 'fake'}
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    monkeypatch.setattr(mod, 'get_discourse_slugs_sites', lambda: (['test'], [site]))
    monkeypatch.setattr(mod, 'get_discourse_site', lambda *args: site)
    monkeypatch.setattr(mod, 'resolve_category', lambda *args: 1)
    class Client:
        def __init__(self, *args, **kwargs): pass
        def create_post(self, body, *args, **kwargs):
            calls.append((body, kwargs))
            if callback: callback()
            return {'topic_id': 7, 'topic_slug': 'report'}
        def upload_file(self, path):
            raise AssertionError('Unrequested audio upload')
    monkeypatch.setattr(mod, 'MmdDiscourseClient', Client)
    return mod


def test_post_saved_report_ignores_unrequested_sidecars_and_rejects_repeat(report_file, monkeypatch):
    report_file.with_suffix('.md').write_text('Stale sidecar')
    report_file.with_suffix('.title').write_text('Old title')
    report_file.with_suffix('.mp3').write_bytes(b'old audio')
    calls = []
    mod = post_setup(monkeypatch, calls)
    monkeypatch.setattr(sys, 'argv', ['st-post', '-s', '6', str(report_file)])
    mod.main()
    assert 'Saved **body 6**' in calls[0][0]
    assert calls[0][1]['title'] == 'Report 6'
    with pytest.raises(SystemExit): mod.main()
    assert len(calls) == 1
    assert read(report_file)['story'][5]['topic_id'] == 7


def test_post_preserves_remote_receipt_if_report_replaced(report_file, monkeypatch):
    def replace():
        current = read(report_file)
        current['story'][5] = edited_report(current['story'][5], 'markdown', 'Replaced')
        report_file.write_text(json.dumps(current))
    mod = post_setup(monkeypatch, [], replace)
    monkeypatch.setattr(sys, 'argv', ['st-post', '-s', '6', str(report_file)])
    mod.main()
    saved = read(report_file)
    assert saved['story'][5]['markdown'] == 'Replaced'
    assert 'post_url' not in saved['story'][5]
    assert saved['_publications'][0]['post_url'].endswith('/7')


def test_post_failure_does_not_clear_metadata(report_file, monkeypatch):
    def fail(): raise RuntimeError('Remote failure')
    mod = post_setup(monkeypatch, [], fail)
    before = report_file.read_bytes()
    monkeypatch.setattr(sys, 'argv', ['st-post', str(report_file)])
    with pytest.raises(SystemExit): mod.main()
    assert report_file.read_bytes() == before


def test_publication_recovery_receipt_when_container_deleted(report_file):
    old = read(report_file)['story'][0]
    report_file.unlink()
    attached, receipt = save_publication(report_file, 0, content_identity(old),
        {'title': 'Title', 'site_url': 'https://forum.example', 'post_url': 'https://forum.example/t/7', 'topic_id': 7, 'mp3_url': ''})
    assert not attached and receipt.is_file()
    assert not report_file.exists()
    assert json.loads(receipt.read_text())['topic_id'] == 7


def test_text_edit_updates_source_markdown_and_invalidates_checks(report_file):
    report = read(report_file)['story'][0]
    edited = edited_report(report, 'text', 'Human plain text')
    assert edited['markdown'] == edited['text'] == 'Human plain text'
    assert edited['fact'] == []


def test_edit_proven_legacy_mapping_survives_manual_body_change(report_file, monkeypatch):
    from _report_store import raw_index, remove_pair
    current = read(report_file)
    for raw, report in zip(current['data'], current['story']):
        raw.pop('data_id')
        report.pop('source_data_id')
        raw['markdown'] = report['markdown']
        raw['prompt'] = f"Original request {report['title']}"
    report_file.write_text(json.dumps(current))
    mod = module('st-edit')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, 'load_cross_env', lambda: None)
    def edit(cmd, **kwargs):
        Path(cmd[-1]).write_text('Edited legacy report')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(mod.subprocess, 'run', edit)
    monkeypatch.setattr(sys, 'argv', ['st-edit', '--markdown', '-s', '3', str(report_file)])
    mod.main()
    saved = read(report_file)
    assert raw_index(saved, 2) == 2
    assert saved['story'][2]['authored_prompt'] == 'Original request Report 3'
    assert len(remove_pair(saved, 2)['data']) == 5


def test_edit_speech_removes_attribution_and_changes_hash():
    from mmd_branding import get_tagline_for_reading
    tag = get_tagline_for_reading('agent', 'model')
    report = {'make': 'agent', 'model': 'model', 'md5_hash': 'old', 'attribution': tag}
    markdown = 'Human edits.\n\n' + tag + '\n\nHuman afterword.'
    result = edited_report(report, 'markdown', markdown)
    assert result['markdown'] == markdown
    assert 'crossai.dev:' not in result['spoken']
    assert 'Human afterword' in result['spoken']
    assert 'This has been a Cross report' in result['spoken']
    assert result['md5_hash'] != 'old'


def test_menu_update_keeps_selected_report(report_file, monkeypatch):
    import discourse
    import mmd_startup
    monkeypatch.setattr(discourse, 'get_discourse_slugs_sites', lambda: ([], []))
    monkeypatch.setattr(mmd_startup, 'load_cross_env', lambda: None)
    mod = module('st')
    mod.file_json = str(report_file)
    mod.story_sel = 2
    mod.fact_sel = 1
    mod.ai = 'chosen-agent'
    mod.execute_menu('Edit', 'u')
    assert mod.cmd == f'st-update --agent chosen-agent -s 2 {report_file}'
    mod.refresh_state()
    assert mod.story_sel == 2
    assert 'st-update' in mod.POST_CMD_REFRESH and 'st-edit' in mod.POST_CMD_REFRESH
    assert not {'A', 'S', 'F'}.intersection(mod.menus['main']['e'][1])


@pytest.mark.parametrize('selection,body', [([], 'body 1'), (['-s', '6'], 'body 6')])
def test_print_ordinary_selection_reads_saved_body(report_file, monkeypatch, selection, body):
    import mmd_startup
    monkeypatch.setattr(mmd_startup, 'load_cross_env', lambda: None)
    monkeypatch.chdir(report_file.parent)
    mod = module('st-print')
    monkeypatch.setattr(mod, 'require_config', lambda: None)
    monkeypatch.setattr(mod, '_WeasyHTML', object())
    rendered = []
    monkeypatch.setattr(mod, '_render_pdf', lambda html: rendered.append(html) or b'%PDF-test')
    monkeypatch.setattr(sys, 'argv', ['st-print', '--save-pdf', *selection, str(report_file)])
    report_file.with_suffix('.md').write_text('Stale sidecar')
    mod.main()
    assert body in rendered[0]
    assert 'Stale sidecar' not in rendered[0]


def test_publication_recovery_failure_explains_remote_success(report_file, monkeypatch):
    from _report_store import StoreError
    report_file.unlink()
    def fail(*args, **kwargs): raise OSError('Disk full')
    monkeypatch.setattr(Path, 'mkdir', fail)
    with pytest.raises(StoreError, match='Post succeeded: https://forum.example/t/7'):
        save_publication(report_file, 0, 'old', {'post_url': 'https://forum.example/t/7'})


def test_post_prompt_legacy_data_only(report_file, monkeypatch):
    report_file.write_text(json.dumps({'data': [{'prompt': 'Legacy request'}], 'story': []}))
    calls = []
    mod = post_setup(monkeypatch, calls)
    monkeypatch.setattr(sys, 'argv', ['st-post', '--prompt', str(report_file)])
    mod.main()
    assert 'Legacy request' in calls[0][0]
    assert read(report_file)['story'] == []


def test_check_does_not_attach_after_removal_shifts_position(report_file):
    current = read(report_file)
    old = current['story'][2]
    del current['story'][1]
    report_file.write_text(json.dumps(current))
    with pytest.raises(ConcurrentWriteError):
        save_fact(report_file, 2, content_identity(old), {'md5_hash': 'stale'}, old['segments'])


def test_publication_merges_concurrent_checks(report_file):
    original = read(report_file)['story'][0]
    save_fact(report_file, 0, content_identity(original), {'md5_hash': 'new'}, original['segments'])
    attached, receipt = save_publication(report_file, 0, content_identity(original),
        {'title': 'Report 1', 'site_url': 'https://forum.example', 'post_url': 'https://forum.example/t/7', 'topic_id': 7, 'mp3_url': ''})
    assert attached and receipt is None
    assert len(read(report_file)['story'][0]['fact']) == 2


def test_post_fact_refuses_wrong_site(report_file, monkeypatch):
    current = read(report_file)
    current['story'][0].update({'post_url': 'https://other.example/t/7', 'topic_id': 7})
    current['story'][0]['fact'][0]['report'] = 'Fact result'
    report_file.write_text(json.dumps(current))
    calls = []
    mod = post_setup(monkeypatch, calls)
    monkeypatch.setattr(sys, 'argv', ['st-post', '-f', '1', str(report_file)])
    with pytest.raises(SystemExit): mod.main()
    assert calls == []


def test_st_update_dispatch_targets_new_script(monkeypatch):
    import commands
    calls = []
    monkeypatch.setattr(commands, '_run', calls.append)
    commands.st_update()
    assert calls == ['st-update']


def test_publication_preserves_legacy_receipt_when_posting_to_another_site(report_file):
    current = read(report_file)
    report = current['story'][0]
    report.update(topic_id=10, post_url='https://old.example/t/10')
    report_file.write_text(json.dumps(current))
    attached, _ = save_publication(report_file, 0, content_identity(report),
        {'title': report['title'], 'site_url': 'https://new.example',
         'post_url': 'https://new.example/t/20', 'topic_id': 20, 'mp3_url': ''})
    assert attached
    assert {r['post_url'] for r in read(report_file)['_publications']} == {
        'https://old.example/t/10', 'https://new.example/t/20'}
