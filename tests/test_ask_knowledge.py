"""Knowledge-source regressions; no AI or telemetry requests."""
import importlib.util
import sys
import re
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'script'))
import build_ask_corpus as builder
from audit_ask_commands import arguments, command_names
from cross_st._ask_match import find_matches


def load_ask():
    spec = importlib.util.spec_from_file_location('ask_knowledge_test', ROOT / 'cross_st/st-ask.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_uses_full_curated_faq():
    assert load_ask()._FAQ == builder.load_faq()


@pytest.mark.parametrize('entry', builder.load_faq(), ids=lambda entry: entry['id'])
def test_canonical_question_and_aliases_return_the_right_answer(entry):
    faq = builder.load_faq()
    for query in [entry['question'], *entry.get('aliases', [])]:
        match = find_matches(query, faq)[0]
        assert match['id'] == entry['id'], query
        assert match['_score'] > 0.6, query


def test_unrelated_question_does_not_return_an_answer():
    matches = find_matches('How do I bake a chocolate cake?', builder.load_faq())
    assert matches[0]['_score'] <= 0.3


def test_alias_results_are_distinct():
    matches = find_matches('install cross-st', builder.load_faq())
    assert len({m['id'] for m in matches}) == len(matches)


def test_faq_links_render_individually(capsys):
    ask = load_ask()
    ask._print_answer({'answer': 'Help', 'see_also': ['https://example.com/a', 'https://example.com/b']}, False)
    out = capsys.readouterr().out
    assert 'Documentation: https://example.com/a' in out
    assert 'Documentation: https://example.com/b' in out


def test_failed_llm_call_is_not_reported_as_a_match(monkeypatch):
    ask = load_ask()
    monkeypatch.setattr(ask.mmd_startup, 'load_cross_env', lambda: None)
    monkeypatch.setattr(ask, '_maybe_prompt_telemetry_consent', lambda: None)
    monkeypatch.setattr(ask, '_has_api_key', lambda: True)
    monkeypatch.setattr(ask, '_select_agent', lambda args: 'test-agent')
    monkeypatch.setattr(ask.ai_handler, 'process_prompt', Mock(side_effect=RuntimeError('failed')))
    report = Mock()
    monkeypatch.setattr(ask, '_report', report)
    monkeypatch.setattr(sys, 'argv', ['st-ask', 'question'])
    ask.main()
    assert report.call_args.kwargs['matched'] is False


def test_corpus_is_current_and_has_every_command():
    assert builder.validate_faq(builder.load_faq()) == []
    expected = builder.assemble_corpus(builder.load_faq(), builder.read_corpus_version())
    assert builder.OUT_PATH.read_text() == expected
    for name in command_names():
        assert (builder.WIKI_DIR / f'{name}.md').is_file()
        assert f'### {name}\n' in expected
        page = (builder.WIKI_DIR / f'{name}.md').read_text()
        documented = set(re.findall(r'--[a-z][a-z0-9_-]*', page))
        section = expected.split('## Current command arguments', 1)[1].split(f'### {name}\n', 1)[1].split('\n### ', 1)[0]
        for names, _ in arguments(name):
            for flag in names:
                assert f'`{flag}`' in section
                if flag.startswith('--'):
                    assert flag in documented, (name, flag)


def test_freshness_check_rejects_stale_corpus(tmp_path, monkeypatch):
    stale = tmp_path / 'support_content.md'
    stale.write_text('old corpus')
    monkeypatch.setattr(builder, 'OUT_PATH', stale)
    monkeypatch.setattr(sys, 'argv', ['build_ask_corpus.py', '--check-current'])
    assert builder.main() == 1
