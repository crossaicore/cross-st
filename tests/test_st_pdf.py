"""PDF command contract and shared renderer regressions; no AI calls."""
import importlib.util
import json
from pathlib import Path
import shlex

import pytest

ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'cross_st' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def export(tmp_path, monkeypatch):
    import mmd_startup
    monkeypatch.setattr(mmd_startup, 'require_config', lambda: None)
    monkeypatch.setattr(mmd_startup, 'load_cross_env', lambda: None)
    monkeypatch.chdir(tmp_path)
    mod = load('st-pdf')
    renderer = load('st-print')
    captured = []
    def render(html, base_url=None):
        captured.append((html, base_url))
        return b'%PDF-test'
    monkeypatch.setattr(renderer, '_render_pdf', render)
    monkeypatch.setattr(renderer, '_print_pdf', lambda *a: pytest.fail('Export must never print'))
    monkeypatch.setattr(mod.runpy, 'run_path', lambda path: {'main': renderer.main})
    source_dir = tmp_path / 'source folder'
    source_dir.mkdir()
    source = source_dir / 'sample.json'
    source.write_text(json.dumps({'story': [
        {'make': 'maker', 'model': 'model-1', 'title': 'First', 'markdown': '# First\n\nFirst body'},
        {'make': 'maker', 'model': 'model-2', 'title': 'Second', 'markdown': '# Second\n\nEdited body'},
    ]}))
    source.with_suffix('.md').write_text('Stale sidecar')
    return mod, renderer, source, captured


@pytest.mark.parametrize('options,expected', [([], 'First body'), (['-s', '2'], 'Edited body')])
def test_export_saved_report_without_modifying_container(export, options, expected):
    mod, _, source, captured = export
    before = source.read_bytes()
    mod.main([*options, str(source)])
    assert Path('sample.pdf').read_bytes() == b'%PDF-test'
    assert expected in captured[0][0] and 'Stale sidecar' not in captured[0][0]
    assert captured[0][1] == str(source.parent)
    assert source.read_bytes() == before


@pytest.mark.parametrize('name,expected', [('My report.pdf', 'My report.pdf'), ('report', 'report.pdf'), ('UPPER.PDF', 'UPPER.PDF')])
def test_output_and_preview(export, monkeypatch, name, expected):
    mod, renderer, source, _ = export
    opened = []
    monkeypatch.setattr(renderer, '_open_pdf', opened.append)
    mod.main(['--story', '2', '-o', name, '--preview', str(source)])
    assert Path(expected).exists()
    assert opened == [expected]
    assert not Path('sample.pdf').exists()


def test_replacement(export):
    mod, _, source, _ = export
    Path('sample.pdf').write_bytes(b'old')
    mod.main([str(source)])
    assert Path('sample.pdf').read_bytes() == b'%PDF-test'


@pytest.mark.parametrize('options', [
    ['--all'], ['--all', '-s', '2'],
    ['-s', '0'], ['-s', '3'], ['-o', 'sample.json'], ['--printer', 'printer'],
])
def test_invalid_options_write_nothing(export, options):
    mod, _, source, captured = export
    before = source.read_bytes()
    with pytest.raises(SystemExit) as error:
        mod.main([*options, str(source)])
    assert error.value.code != 0
    assert not captured
    assert source.read_bytes() == before
    assert not list(Path.cwd().glob('*.pdf'))


def test_quiet_wins_over_verbose(export, capsys):
    mod, _, source, _ = export
    mod.main(['-q', '-v', str(source)])
    assert not capsys.readouterr().out


def test_unwritable_output_is_readable_error(export, capsys):
    mod, _, source, _ = export
    with pytest.raises(SystemExit) as error:
        mod.main(['-o', 'missing/report.pdf', str(source)])
    assert error.value.code == 1
    assert 'Could not save PDF' in capsys.readouterr().err


@pytest.mark.parametrize('contents', ['not json', '[]', '{"story": []}', '{"story": [7]}'])
def test_invalid_container_fails_before_render(export, contents):
    mod, _, source, captured = export
    source.write_text(contents)
    with pytest.raises(SystemExit):
        mod.main([str(source)])
    assert not captured


def test_pdf_metadata_and_markdown(export):
    _, renderer, _, _ = export
    if renderer._WeasyHTML is None:
        pytest.skip('WeasyPrint native libraries unavailable')
    html = renderer._build_html({
        'title': 'A & B "title"', 'make': 'Provider <one>', 'model': 'model&2',
        'markdown': '# Report\n\n**Bold** [source](https://example.org)\n\n| A | B |\n|---|---|\n| 1 | 2 |',
    }, 2, 3, 'report & sample.json')
    document = renderer._WeasyHTML(string=html).render()
    assert document.metadata.title == 'A & B "title"'
    assert document.metadata.authors == ['Provider <one> / model&2']
    assert document.metadata.generator == 'Cross — Maker Matt Design'
    assert 'https://crossai.dev' in document.metadata.description
    assert document.metadata.created
    assert '<strong>Bold</strong>' in html and '<table>' in html
    assert 'Provider &lt;one&gt;' in html
    assert document.write_pdf().startswith(b'%PDF-')


def test_menu_exports_current_report_with_spaces(monkeypatch):
    import discourse
    import mmd_startup
    monkeypatch.setattr(discourse, 'get_discourse_slugs_sites', lambda: ([], []))
    monkeypatch.setattr(mmd_startup, 'load_cross_env', lambda: None)
    mod = load('st')
    mod.file_json = '/tmp/My reports.json'
    mod.story_sel = 2
    mod.execute_menu('Post', 'd')
    assert shlex.split(mod.cmd) == ['st-pdf', '-s', '2', '/tmp/My reports.json']
    mod.execute_menu('Post', 'D')
    assert shlex.split(mod.cmd) == ['st-print', '-s', '2', '/tmp/My reports.json']


def test_legacy_print_defaults_to_printer(export, monkeypatch):
    _, renderer, source, _ = export
    printed = []
    monkeypatch.setattr(renderer, '_print_pdf', lambda *args: printed.append(args))
    renderer.main(['-s', '2', '--printer', 'Office', str(source)])
    assert printed == [(b'%PDF-test', 'Office', False)]
    assert not list(Path.cwd().glob('*.pdf'))


def test_legacy_export_cannot_overwrite_container(export):
    _, renderer, source, captured = export
    before = source.read_bytes()
    with pytest.raises(SystemExit):
        renderer.main(['--output', str(source), str(source)])
    assert source.read_bytes() == before
    assert not captured


def test_missing_renderer_explains_setup(export, monkeypatch, capsys):
    mod, renderer, source, _ = export
    # Restore the real renderer after the fixture's byte-only stub.
    monkeypatch.setattr(renderer, '_render_pdf', load('st-print')._render_pdf)
    renderer._render_pdf.__globals__['_WeasyHTML'] = None
    with pytest.raises(SystemExit) as error:
        mod.main([str(source)])
    assert error.value.code == 1
    assert 'Pango/GObject' in capsys.readouterr().out


@pytest.mark.parametrize('options,filename', [
    ([], 'sample_report2_fact1.pdf'),
    (['--output', 'Review.pdf'], 'Review.pdf'),
])
def test_export_fact_check(export, options, filename):
    mod, _, source, captured = export
    container = json.loads(source.read_text())
    container['story'][1]['fact'] = [
        {'make': 'evaluator', 'model': 'review-model', 'report': '# Review\n\nChecked evidence.'},
    ]
    source.write_text(json.dumps(container))
    before = source.read_bytes()
    mod.main(['-s', '2', '--fact', '1', *options, str(source)])
    html = captured[0][0]
    assert Path(filename).exists()
    assert 'Checked evidence.' in html and 'Edited body' not in html
    assert 'evaluator' in html and 'review-model' in html
    assert 'Report 2 of 2' in html and 'Fact-check 1' in html
    assert '<title>Fact-check 1 — Second</title>' in html
    assert source.read_bytes() == before


@pytest.mark.parametrize('index,facts', [(0, []), (1, []), (2, [{'report': 'One'}]),
                                       (1, [{'report': ''}]), (1, [None])])
def test_invalid_fact_check_writes_nothing(export, index, facts):
    mod, _, source, captured = export
    container = json.loads(source.read_text())
    container['story'][0]['fact'] = facts
    source.write_text(json.dumps(container))
    with pytest.raises(SystemExit):
        mod.main(['-f', str(index), str(source)])
    assert not captured
    assert not list(Path.cwd().glob('*.pdf'))


def test_print_all_cannot_select_fact_check(export):
    _, renderer, source, captured = export
    with pytest.raises(SystemExit):
        renderer.main(['--all', '-f', '1', str(source)])
    assert not captured
