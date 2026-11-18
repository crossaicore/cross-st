"""End-to-end update orchestration with an AI double and real temporary containers."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import _report_store as store
import _report_update as engine
import ai_handler


@pytest.fixture
def cli():
    path = Path(__file__).parents[1] / 'cross_st' / 'st-update.py'
    spec = importlib.util.spec_from_file_location('st_update_simple_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def response(monkeypatch):
    state = SimpleNamespace(calls=[], markdown='# New report\n\nUpdated facts.\n\nMy human closing note.', error=None, hook=None)
    monkeypatch.setattr(engine, 'get_ai_list', lambda: ['test-agent'])
    monkeypatch.setattr(engine, 'get_ai_make', lambda agent: 'test-provider')
    monkeypatch.setattr(engine, 'get_ai_model', lambda agent: 'test-model')
    monkeypatch.setattr(ai_handler, 'get_default_ai', lambda: 'test-agent')
    monkeypatch.setattr(ai_handler, 'check_api_key', lambda agent: True)
    monkeypatch.setattr(engine, 'get_content_auto', lambda raw: raw['content'])
    monkeypatch.setattr(engine, 'get_usage', lambda *args: {'total_tokens': 20})

    class Response(tuple):
        was_cached = False

    def call(agent, prompt, **kwargs):
        state.calls.append((agent, prompt, kwargs))
        if state.hook:
            state.hook()
        if state.error:
            raise state.error
        content = state.content if hasattr(state, 'content') else json.dumps({
            'markdown': state.markdown,
            'changes': [{'description': 'Updated facts.', 'reason': 'Requested correction.',
                         'sources': ['request', 'source'], 'uncertainty': 'Supplied evidence only.'}],
            'uncertainties': ['No live research was performed.'],
        })
        return Response(({'prompt': prompt}, None, {'content': content}, 'returned-model'))

    monkeypatch.setattr(engine, 'process_prompt', call)
    return state


@pytest.fixture
def files(tmp_path):
    path = tmp_path / 'report with spaces.json'
    source = {'make': 'test-agent', 'model': 'test-model', 'title': 'Original',
              'markdown': '# Original\n\nOld facts.\n\nMy human closing note.',
              'text': 'Old facts.', 'spoken': 'Old facts.', 'fact': [{'old': True}],
              'segments': ['stale'], 'post_id': 77}
    original = {'data': [{'make': 'test-agent', 'model': 'test-model', 'prompt': 'Original standing brief.'}],
                'story': [source], 'custom': {'keep': True}}
    path.write_text(json.dumps(original))
    prompt = tmp_path / 'request.prompt'
    prompt.write_text('Correct the facts; preserve my closing note.')
    return path, prompt, original


def args(cli, files, *flags):
    path, prompt, _ = files
    return cli.parser_for_cli().parse_args([str(path), '--prompt', str(prompt), *flags])


def read(path):
    return json.loads(path.read_text())


def test_append_is_a_complete_ordinary_report(cli, files, response, capsys):
    path, _, original = files
    assert cli.run(args(cli, files, '--update-details', '--no-cache')) == 0
    saved = read(path)
    assert len(saved['story']) == len(saved['data']) == 2
    assert {k: v for k, v in saved['story'][0].items() if k not in ('source_data_id', 'authored_prompt')} == original['story'][0]
    assert {k: v for k, v in saved['data'][0].items() if k != 'data_id'} == original['data'][0]
    assert saved['story'][0]['source_data_id'] == saved['data'][0]['data_id']
    assert saved['custom'] == original['custom']
    out, raw = saved['story'][1], saved['data'][1]
    assert out['source_data_id'] == raw['data_id']
    assert out['fact'] == [] and 'segments' not in out and 'post_id' not in out
    assert out['title'] == 'New report' and out['model'] == 'returned-model'
    assert raw['base_prompt'] == 'Original standing brief.'
    assert raw['prompt'] == raw['update_request'] == out['authored_prompt']
    assert out['markdown'].count(out['attribution']) == 1
    assert 'Updated facts' in out['text'] and 'Updated facts' in out['spoken']
    assert not ({'revisions', 'revision_schema_version', 'active_report'} & saved.keys())
    assert len(response.calls) == 1 and response.calls[0][2]['use_cache'] is False
    assert 'My human closing note.' in response.calls[0][1]
    output = capsys.readouterr().out
    assert 'Saved report 2' in output and 'Exact Markdown changes' in output
    assert "-s 2 '" in output and 'not independently verified' in output


@pytest.mark.parametrize('flags', [[], ['--iterate', '1']])
def test_multiple_sources_require_selection_before_ai(cli, files, response, flags):
    path, _, original = files
    original['story'].append(deepcopy(original['story'][0]))
    path.write_text(json.dumps(original))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='explicit source'):
        cli.run(args(cli, files, *flags))
    assert not response.calls and path.read_bytes() == before


@pytest.mark.parametrize('flags', [['-s', '0'], ['-s', '2'], ['--iterate', '0'], ['--iterate', '2']])
def test_nonexistent_indices_rejected_even_first_call(cli, files, response, flags):
    path, _, _ = files
    before = path.read_bytes()
    with pytest.raises(ValueError, match='does not exist'):
        cli.run(args(cli, files, *flags))
    assert not response.calls and path.read_bytes() == before


def test_first_iterate_existing_index_is_ignored(cli, files, response, capsys):
    cli.run(args(cli, files, '--iterate', '1'))
    assert len(read(files[0])['story']) == 2
    assert 'Ignoring --iterate' in capsys.readouterr().out


def test_iterate_uses_selected_source_and_replaces_both_entries(cli, files, response):
    path, prompt, _ = files
    cli.run(args(cli, files))
    original = read(path)
    original['story'][1]['markdown'] += '\nTarget-only manual edit.'
    original['story'][1]['fact'] = [{'old-check': 1}]
    path.write_text(json.dumps(original))
    prompt.write_text('Replace the old output with new facts.')
    response.markdown = '# Final\n\nEntirely new facts.'
    cli.run(args(cli, files, '-s', '1', '--iterate', '2'))
    result = read(path)
    assert len(result['data']) == len(result['story']) == 2
    assert result['story'][0] == original['story'][0]
    assert result['data'][1]['data_id'] == original['data'][1]['data_id']
    assert 'Entirely new facts.' in result['data'][1]['gen_response']['content']
    assert 'Updated facts.' not in json.loads(result['data'][1]['gen_response']['content'])['markdown']
    assert result['story'][1]['fact'] == []
    assert 'Target-only manual edit.' not in response.calls[-1][1]
    assert 'My human closing note.' in response.calls[-1][1]


def test_same_source_and_target_captures_edited_source(cli, files, response):
    path, prompt, _ = files
    cli.run(args(cli, files))
    saved = read(path)
    saved['story'][1]['markdown'] += '\nHuman table correction.'
    path.write_text(json.dumps(saved))
    prompt.write_text('Keep the table correction.')
    cli.run(args(cli, files, '-s', '2', '--iterate', '2'))
    assert 'Human table correction.' in response.calls[-1][1]
    assert read(path)['data'][1]['base_prompt'] == 'Original standing brief.'
    assert 'Update the supplied source' not in read(path)['data'][1]['base_prompt']


def test_nonupdate_target_refused_after_first_update(cli, files, response):
    cli.run(args(cli, files))
    with pytest.raises(ValueError, match='raw data entry|iterative update prompt'):
        cli.run(args(cli, files, '-s', '1', '--iterate', '1'))
    assert len(response.calls) == 1


@pytest.mark.parametrize('failure', ['api', 'json', 'empty', 'unknown_source', 'prepare', 'commit'])
def test_iteration_failures_preserve_complete_old_pair(cli, files, response, monkeypatch, failure):
    path, _, _ = files
    cli.run(args(cli, files))
    before = path.read_bytes()
    if failure == 'api':
        response.error = RuntimeError('AI failed')
    elif failure == 'json':
        response.content = 'not JSON'
    elif failure == 'empty':
        response.markdown = ' '
    elif failure == 'unknown_source':
        response.content = json.dumps({'markdown': 'text', 'changes': [{'description': 'x', 'reason': 'x', 'uncertainty': '', 'sources': ['invented']}], 'uncertainties': []})
    else:
        def fail(*args, **kwargs):
            raise ValueError('cannot prepare/save')
        monkeypatch.setattr(engine if failure == 'prepare' else store,
                            'prepare_report' if failure == 'prepare' else '_replace', fail)
    with pytest.raises((ValueError, RuntimeError)):
        cli.run(args(cli, files, '-s', '1', '--iterate', '2'))
    assert path.read_bytes() == before


def test_concurrent_modification_is_not_overwritten(cli, files, response):
    path, _, _ = files
    cli.run(args(cli, files))
    other = read(path)
    other['custom']['other_editor'] = True
    response.hook = lambda: path.write_text(json.dumps(other))
    with pytest.raises(store.ConcurrentWriteError):
        cli.run(args(cli, files, '-s', '1', '--iterate', '2'))
    assert read(path) == other


def test_show_saved_summary_needs_no_agent_and_never_writes(cli, files, response, monkeypatch, capsys):
    path, _, _ = files
    cli.run(args(cli, files))
    saved = read(path)
    saved['story'][1]['markdown'] += '\nManual correction.'
    path.write_text(json.dumps(saved))
    before = path.read_bytes()
    monkeypatch.setattr(engine, 'identity', lambda agent: pytest.fail('agent resolved for a read'))
    command = cli.parser_for_cli().parse_args([str(path), '-s', '2', '--show-summary', '--update-details'])
    assert cli.run(command) == 0
    assert path.read_bytes() == before and len(response.calls) == 1
    assert 'edited since generation' in capsys.readouterr().out


def test_evidence_and_size_validation_before_ai(cli, files, response, tmp_path, monkeypatch):
    evidence = tmp_path / 'notes.md'
    evidence.write_text('New supplied measurements.')
    cli.run(args(cli, files, '--evidence', str(evidence)))
    assert 'New supplied measurements.' in response.calls[0][1]
    before = files[0].read_bytes()
    monkeypatch.setenv('CROSS_UPDATE_MAX_INPUT_BYTES', '10')
    with pytest.raises(ValueError, match='exceed'):
        cli.run(args(cli, files, '-s', '1'))
    assert len(response.calls) == 1 and files[0].read_bytes() == before


def test_empty_request_is_noop(cli, files, response):
    path, prompt, _ = files
    before = path.read_bytes()
    prompt.write_text('  ')
    assert cli.run(args(cli, files)) == 0
    assert not response.calls and path.read_bytes() == before


def test_iterate_editor_reopens_request_and_keeps_failed_draft(cli, files, response, monkeypatch):
    path, prompt, _ = files
    cli.run(args(cli, files))
    monkeypatch.setattr(cli.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setenv('EDITOR', 'my-editor --wait')
    seen = []
    def editor(command, **kwargs):
        assert command[:2] == ['my-editor', '--wait']
        draft = Path(command[-1])
        seen.append(draft)
        assert draft.read_text() == prompt.read_text()
        draft.write_text('My revised instructions')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(cli.subprocess, 'run', editor)
    response.error = RuntimeError('AI offline')
    command = cli.parser_for_cli().parse_args([str(path), '-s', '1', '--iterate', '2', '--no-spell'])
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        cli.run(command)
    assert path.read_bytes() == before and seen[0].read_text() == 'My revised instructions'


def test_exact_diff_counts_content_starting_with_plus(cli, files, response):
    response.markdown = '# Original\n\n+++ an added content line'
    cli.run(args(cli, files))
    summary = read(files[0])['data'][1]['update_summary']
    assert summary['added_lines'] == 1


def test_five_initial_reports_append_to_six(cli, files, response):
    path, _, original = files
    original['story'] *= 5
    original['data'] *= 5
    path.write_text(json.dumps(original))
    cli.run(args(cli, files, '-s', '3'))
    saved = read(path)
    assert len(saved['story']) == len(saved['data']) == 6
    assert [{k: v for k, v in report.items() if k != 'authored_prompt'} for report in saved['story'][:5]] == original['story']
    assert all(report['authored_prompt'] == 'Original standing brief.' for report in saved['story'][:5])
    assert saved['story'][5]['source_data_id'] == saved['data'][5]['data_id']


def test_cat_selects_update_request(cli, files, response, monkeypatch, capsys):
    cli.run(args(cli, files))
    path = Path(__file__).parents[1] / 'cross_st' / 'st-cat.py'
    spec = importlib.util.spec_from_file_location('st_cat_update_test', path)
    cat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cat)
    monkeypatch.setattr(cat, 'require_config', lambda: None)
    monkeypatch.setattr(cat.sys, 'argv', ['st-cat', '-s', '2', '--prompt', str(files[0])])
    capsys.readouterr()
    cat.main()
    assert capsys.readouterr().out.strip() == files[1].read_text()


def test_update_preserves_distinct_manual_title_when_heading_unchanged(cli, files, response):
    path, _, original = files
    original['story'][0]['title'] = 'Distinct publishing title'
    path.write_text(json.dumps(original))
    response.markdown = '# Original\n\nUpdated figures.'
    cli.run(args(cli, files))
    assert read(path)['story'][1]['title'] == 'Distinct publishing title'


def test_known_attribution_before_human_note_is_not_duplicated(cli, files, response):
    from mmd_branding import get_tagline_for_reading
    path, _, original = files
    old_tag = get_tagline_for_reading('test-agent', 'test-model')
    original['story'][0]['markdown'] += '\n\n' + old_tag + '\n\nMy additional human note.'
    path.write_text(json.dumps(original))
    response.markdown += '\n\n' + old_tag + '\n\nMy additional human note.'
    cli.run(args(cli, files))
    assert old_tag not in response.calls[0][1]
    assert 'My additional human note.' in response.calls[0][1]
    out = read(path)['story'][1]
    assert out['markdown'].count('crossai.dev:') == 1
    assert 'My additional human note.' in out['markdown']
