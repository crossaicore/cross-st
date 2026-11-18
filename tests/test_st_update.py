"""End-to-end update workflows with real storage and mocked provider calls."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import _report_revisions as revisions
import _update_plan as engine


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location('st_update_cli', Path(__file__).parents[1] / 'cross_st/st-update.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def files(tmp_path):
    path = tmp_path / 'report with spaces.json'
    path.write_text(json.dumps({'extension': 'retain', 'data': [{'prompt': 'Write for beginners.'}],
                               'story': [{'title': 'My title', 'markdown': '# My title\n\nOriginal claim.',
                                          'fact': [{'score': 7}]}]}))
    prompt = tmp_path / 'changes with spaces.prompt'
    prompt.write_text('Add the supplied result: there were 12 observations.')
    return path, prompt


@pytest.fixture
def provider(monkeypatch):
    calls = []
    proposal = {'summary': 'Add the supplied observation count.', 'preserve': ['Title and original claim'],
                'uncertainties': ['No independent verification'], 'questions': [],
                'changes': [{'id': 'U1', 'target': 'Results', 'current': '', 'proposed': 'Add 12 observations.',
                             'reason': 'Requested addition', 'kind': 'supplied_fact', 'sources': ['request'], 'uncertainty': ''}]}
    monkeypatch.setattr(engine, 'get_ai_list', lambda: ['editor'])
    monkeypatch.setattr(engine, 'get_ai_make', lambda _: 'fixture')
    monkeypatch.setattr(engine, 'get_ai_model', lambda _: 'model-one')
    monkeypatch.setattr(engine, 'get_usage', lambda *_: {'input_tokens': 4, 'output_tokens': 5, 'total_tokens': 9})
    monkeypatch.setattr(engine, 'get_content_auto', lambda r: r['body'])
    import ai_handler
    monkeypatch.setattr(ai_handler, 'get_default_ai', lambda: 'editor')
    class Response:
        was_cached = True
        def __init__(self, content): self.content = content
        def __iter__(self): return iter(({}, None, {'body': self.content}, 'model-one'))
    def call(agent, prompt, **kwargs):
        calls.append((agent, prompt, kwargs))
        if 'APPROVED PLAN:' in prompt:
            return Response('# My title\n\nOriginal claim.\n\nThere were 12 observations.')
        return Response(json.dumps(proposal))
    monkeypatch.setattr(engine, 'process_prompt', call)
    return calls, proposal


def args(cli, files, *options):
    return cli.parser_for_cli().parse_args([str(files[0]), *options])


def review(cli, files):
    assert cli.run(args(cli, files, '--prompt', str(files[1]), '--review-only')) == 0
    return next((files[0].parent / '.cross-update').glob('*.plan'))


def test_review_apply_and_replay_keep_history(cli, files, provider, capsys):
    before = files[0].read_bytes()
    plan = review(cli, files)
    assert files[0].read_bytes() == before
    assert len(provider[0]) == 1
    assert cli.run(args(cli, files, '--apply-plan', str(plan))) == 0
    container, _ = revisions.load_snapshot(files[0])
    assert len(container['story']) == 2
    assert container['story'][0]['fact'] == [{'score': 7}]
    assert container['story'][1]['fact'] == []
    assert revisions.selected_indices(container) == [1]
    assert 'Report v2 · Based on v1' in revisions.render_report(container['story'][1])
    assert container['extension'] == 'retain'
    assert len(provider[0]) == 2
    assert cli.run(args(cli, files, '--apply-plan', str(plan))) == 0
    assert len(provider[0]) == 2
    assert len(revisions.load_snapshot(files[0])[0]['story']) == 2
    assert 'already applied' in capsys.readouterr().out


def test_dry_run_writes_nothing_and_calls_nothing(cli, files, provider):
    before = files[0].read_bytes()
    assert cli.run(args(cli, files, '--prompt', str(files[1]), '--dry-run')) == 0
    assert files[0].read_bytes() == before
    assert not list(files[0].parent.glob('.cross-update'))
    assert provider[0] == []


def test_stale_plan_rejected_before_generation(cli, files, provider):
    plan = review(cli, files)
    container = json.loads(files[0].read_text())
    container['other'] = 'concurrent change'
    files[0].write_text(json.dumps(container))
    before = files[0].read_bytes()
    with pytest.raises(ValueError, match='changed'):
        cli.run(args(cli, files, '--apply-plan', str(plan)))
    assert files[0].read_bytes() == before and len(provider[0]) == 1


def test_quiet_review_details_and_empty_enter_do_not_approve(cli, files, provider, monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    choices = iter(['', 'details', 'summary', 'cancel'])
    monkeypatch.setattr('builtins.input', lambda _: next(choices))
    before = files[0].read_bytes()
    assert cli.run(args(cli, files, '--prompt', str(files[1]), '--quiet')) == 0
    assert files[0].read_bytes() == before and len(provider[0]) == 1
    output = capsys.readouterr().out
    assert 'Current:' in output and 'Source request:' in output and 'Enter does not approve' in output


def test_revision_requires_new_plan_then_approval(cli, files, provider, monkeypatch):
    monkeypatch.setattr(cli.sys, 'stdin', SimpleNamespace(isatty=lambda: True))
    choices = iter(['revise', 'approve'])
    monkeypatch.setattr('builtins.input', lambda _: next(choices))
    monkeypatch.setattr(cli, 'edit_request', lambda *_: ('Add 12 observations and preserve title.', None))
    assert cli.run(args(cli, files, '--prompt', str(files[1]))) == 0
    assert len(provider[0]) == 3
    container = revisions.load_snapshot(files[0])[0]
    assert container['revisions'][-1]['change_request'] == 'Add 12 observations and preserve title.'


def test_unresolved_questions_cannot_be_applied(cli, files, provider):
    provider[1]['questions'] = ['Which result should be included?']
    plan = review(cli, files)
    before = files[0].read_bytes()
    with pytest.raises(ValueError, match='questions'):
        cli.run(args(cli, files, '--apply-plan', str(plan)))
    assert files[0].read_bytes() == before and len(provider[0]) == 1


def test_failed_check_preserves_saved_report(cli, files, provider, monkeypatch):
    plan = review(cli, files)
    commands = []
    def check(command, **_):
        commands.append(command)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(cli.subprocess, 'run', check)
    assert cli.run(args(cli, files, '--apply-plan', str(plan), '--check')) == 3
    assert len(revisions.load_snapshot(files[0])[0]['story']) == 2
    assert commands[0][commands[0].index('--story') + 1] == '2'


def test_noninteractive_generation_rejected_before_calls(cli, files, provider):
    parser = cli.parser_for_cli()
    with pytest.raises(SystemExit) as exc:
        cli.validate_options(parser, args(cli, files, '--prompt', str(files[1])), False)
    assert exc.value.code == 2 and not provider[0]


@pytest.mark.parametrize('options', [
    ['--apply-plan', 'saved.plan', '--prompt', 'changes.prompt'],
    ['--review-only', '--check', '--prompt', 'changes.prompt'],
    ['--dry-run'], ['--history', '--update-details'],
    ['--draft-only', '--update-summary'],
])
def test_invalid_modes_fail_early(cli, files, options):
    with pytest.raises(SystemExit):
        cli.validate_options(cli.parser_for_cli(), args(cli, files, *options), True)


def test_history_and_activation_have_no_ai(cli, files, provider, capsys):
    plan = review(cli, files)
    cli.run(args(cli, files, '--apply-plan', str(plan)))
    container = revisions.load_snapshot(files[0])[0]
    assert cli.run(args(cli, files, '--activate', container['revisions'][0]['id'])) == 0
    assert cli.run(args(cli, files, '--history')) == 0
    assert revisions.selected_indices(revisions.load_snapshot(files[0])[0]) == [0]
    assert len(provider[0]) == 2
    assert 'Report v2' in capsys.readouterr().out


def test_preparation_recovery_makes_no_additional_paid_call(cli, files, provider, monkeypatch):
    plan = review(cli, files)
    prepare = engine.prepare_report
    def fail(*_):
        raise ValueError('temporary preparation problem')
    monkeypatch.setattr(engine, 'prepare_report', fail)
    with pytest.raises(ValueError, match='Raw response retained'):
        cli.run(args(cli, files, '--apply-plan', str(plan)))
    assert len(provider[0]) == 2
    attempt = next((files[0].parent / '.cross-update').glob('*.attempt'))
    monkeypatch.setattr(engine, 'prepare_report', prepare)
    assert cli.run(args(cli, files, '--recover-attempt', str(attempt))) == 0
    assert len(provider[0]) == 2
    assert len(revisions.load_snapshot(files[0])[0]['story']) == 2
    assert cli.run(args(cli, files, '--recover-attempt', str(attempt))) == 0
    assert len(provider[0]) == 2


def test_tampered_recovery_response_rejected(cli, files, provider, monkeypatch):
    plan = review(cli, files)
    def fail(*_):
        raise ValueError('temporary preparation problem')
    monkeypatch.setattr(engine, 'prepare_report', fail)
    with pytest.raises(ValueError):
        cli.run(args(cli, files, '--apply-plan', str(plan)))
    attempt = next((files[0].parent / '.cross-update').glob('*.attempt'))
    saved = json.loads(attempt.read_text())
    saved['body'] = 'unreviewed alteration'
    attempt.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='changed or was damaged'):
        cli.run(args(cli, files, '--recover-attempt', str(attempt)))
    assert len(provider[0]) == 2
