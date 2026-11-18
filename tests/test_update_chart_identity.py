"""Updated reports remain independent candidates without changing AI metadata."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from _report_signals import report_author_key, report_prompt_signals, score_authors
from mmd_data_analysis import get_flattened_fc_data


def load_script(script):
    path = Path(__file__).parents[1] / "cross_st" / f"{script}.py"
    spec = importlib.util.spec_from_file_location(script.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def six_reports():
    container = {"_st_update": True, "data": [], "story": []}
    for i in range(6):
        provider = f"provider{i % 5}"
        raw = {"data_id": f"raw{i}", "make": provider, "model": "model", "prompt": "Write 100 words."}
        report = {"source_data_id": raw["data_id"], "make": provider, "model": "model",
                  "markdown": "word " * 100, "authored_prompt": "Write 100 words.",
                  "fact": [{"make": "checker", "model": "check", "counts": [20-2*i, 0, 0, 0, 2*i], "score": 2-i/10}]}
        if i == 5:
            raw["update_request"] = "Write 100 words with the new observations."
        container["data"].append(raw)
        container["story"].append(report)
    return container


def test_six_candidates_keep_distinct_scores_and_physical_labels(six_reports):
    before = copy.deepcopy(six_reports)
    scores = score_authors(six_reports)
    assert len(scores) == 6
    by_index = {score.report_index: score for score in scores}
    assert by_index[1].author == "provider0:model [S1]"
    assert by_index[6].author == "provider0:model [S6]"
    assert by_index[1].components["accuracy"] != by_index[6].components["accuracy"]
    assert six_reports == before


@pytest.mark.parametrize("script", ["st-heatmap", "st-plot", "st-verdict"])
def test_chart_axes_keep_six_reports_and_real_checker_metadata(six_reports, script):
    module = load_script(script)
    flat = get_flattened_fc_data(six_reports)
    assert len(flat) == 6  # No square-matrix reduction can discard the update.
    frame = module._chart_frame(flat)
    assert frame["target"].nunique() == 6
    assert set(frame["evaluator"]) == {"checker:check"}
    assert frame.iloc[5]["evaluator_make"] == "provider0"
    assert frame.iloc[5]["evaluator_model"] == "model"
    assert frame.iloc[5]["target"] == "provider0:model [S6]"


def test_authored_requirement_overrides_base_without_using_other_report(six_reports):
    report = six_reports["story"][5]
    report["base_prompt"] = "Write 1000 words about workshops."
    report["authored_prompt"] = "Write 200 words about attendance."
    assert report_prompt_signals(six_reports, 5).target_words == 200
    assert report_prompt_signals(six_reports, 0).target_words == 100


def test_raw_association_recognizes_agent_alias_as_author(six_reports):
    six_reports["data"][5]["make"] = "configured-agent-name"
    score = next(score for score in score_authors(six_reports) if score.report_index == 6)
    assert "evaluator-only" not in (score.excluded_reason or "")


def test_legacy_unique_author_label_unchanged():
    container = {"story": [{"make": "provider", "model": "model"}]}
    assert report_author_key(container, 0) == "provider:model"


def test_duplicate_authors_without_update_marker_still_distinct():
    container = {"story": [{"make": "provider", "model": "model"}] * 2}
    assert report_author_key(container, 1) == "provider:model [S2]"


@pytest.mark.parametrize("selection,expected", [([], 6), (["-s", "1"], 1)])
def test_verdict_winner_uses_physical_index_and_explicit_selection_wins(
        six_reports, tmp_path, monkeypatch, selection, expected):
    import _report_signals
    from types import SimpleNamespace
    module = load_script("st-verdict")
    path = tmp_path / "reports.json"
    path.write_text(json.dumps(six_reports))
    monkeypatch.setattr(module, "require_config", lambda: None)
    monkeypatch.setattr(module, "load_cross_env", lambda: None)
    monkeypatch.setattr(module, "score_authors", lambda *a, **k: [
        SimpleNamespace(excluded=False, report_index=6, author="provider0:model [S6]")])

    class Selected(Exception):
        pass

    def collect(container, index, lens):
        assert index == expected
        raise Selected

    monkeypatch.setattr(module, "collect_lens_claims", collect)
    monkeypatch.setattr("sys.argv", ["st-verdict", str(path), "--what-is-false", "--no-display", "-q", *selection])
    with pytest.raises(Selected):
        module.main()
