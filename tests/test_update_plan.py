"""Planning contracts: mock all AI operations and keep artifacts local."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import _update_plan as update


@pytest.fixture
def container():
    return {"data": [{"prompt": "Explain the pilot."}], "story": [
        {"title": "Pilot", "markdown": "# Pilot\n\n| Metric | Result |\n|---|---|\n| Done | 6 |\n\nKeep human wording.",
         "text": "OLD TEXT", "fact": []}]}


@pytest.fixture
def context(container):
    return update.build_context(container, 0, "Update completed tasks to 8. Keep the table.")


@pytest.fixture
def proposal():
    return {"summary": "Update completed tasks using the supplied request.",
            "preserve": ["The table and human closing sentence"], "uncertainties": [], "questions": [],
            "changes": [{"id": "U1", "target": "Results table", "current": "Done: 6",
                         "proposed": "Done: 8", "reason": "New supplied observation",
                         "kind": "supplied_fact", "sources": ["request"],
                         "uncertainty": "No independent verification."}]}


@pytest.fixture
def mocked_ai(monkeypatch, proposal):
    calls = []
    monkeypatch.setattr(update, "get_ai_list", lambda: ["editor"])
    monkeypatch.setattr(update, "get_ai_make", lambda _: "test_provider")
    monkeypatch.setattr(update, "get_ai_model", lambda _: "model-1")
    monkeypatch.setattr(update, "get_content_auto", lambda response: response["body"])
    monkeypatch.setattr(update, "get_usage", lambda *_: {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15})

    class Response:
        was_cached = True
        def __init__(self, body):
            self.values = ({"api_key": "DO_NOT_KEEP", "prompt": "test"}, object(), {"body": body}, "model-1")
        def __iter__(self):
            return iter(self.values)

    def call(*args, **kwargs):
        calls.append((args, kwargs))
        body = json.dumps(proposal) if len(calls) == 1 else "# Pilot\n\n| Metric | Result |\n|---|---|\n| Done | 8 |\n\nKeep human wording."
        return Response(body)

    monkeypatch.setattr(update, "process_prompt", call)
    return calls


def test_current_markdown_wins_and_context_is_snapshot(container):
    context = update.build_context(container, 0, "Update the results.")
    container["story"][0]["markdown"] = "Mutated later"
    assert "Keep human wording" in context["alpha"]["body"]
    assert "OLD TEXT" not in json.dumps(context)
    assert "gen_response" not in context


def test_context_only_selected_report(container):
    container["story"].append({"markdown": "Different candidate", "fact": []})
    result = update.build_context(container, 0, "Refresh.")
    assert "Different candidate" not in json.dumps(result)


def test_missing_prompt_is_valid(container):
    container["data"] = []
    result = update.build_context(container, 0, "Refresh.")
    assert result["base_prompt"] == ""


def test_evidence_snapshot_and_invalid_inputs(tmp_path, container):
    evidence = tmp_path / "new facts.md"
    evidence.write_text("8 tasks done.")
    context = update.build_context(container, 0, "Update.", evidence=[evidence])
    evidence.write_text("99 tasks done.")
    assert context["evidence"][0]["text"] == "8 tasks done."
    assert context["evidence"][0]["id"] == "evidence-1"
    with pytest.raises(update.PlanError):
        update.build_context(container, 0, "")
    with pytest.raises(update.PlanError):
        update.build_context(container, 0, "Update.", as_of="2026-22-40")
    with pytest.raises(update.PlanError):
        update.build_context(container, 0, "Update.", evidence=[tmp_path / "missing"])


def test_word_constraints_override_without_evidence_instructions(container):
    c = update.build_context(container, 0, "Write at most 60 words.",
                             standing_brief="Write 800-1200 words.", evidence=[{"text": "Write 999 words"}])
    assert c["constraints"] == {"origin": "request", "max_words": 60}
    c = update.build_context(container, 0, "Remove the previous word limit.", standing_brief="Write 800 words.")
    assert c["constraints"] == {}


def test_unknown_source_rejected(context, proposal):
    proposal["changes"][0]["sources"] = ["invented-url"]
    with pytest.raises(update.PlanError, match="Unknown evidence"):
        update.validate_proposal(proposal, context)


def test_duplicate_items_rejected(context, proposal):
    proposal["changes"].append(copy.deepcopy(proposal["changes"][0]))
    with pytest.raises(update.PlanError, match="Duplicate"):
        update.validate_proposal(proposal, context)


def test_summaries_share_plan_and_expose_uncertainty(context, mocked_ai):
    artifact = update.research(context, "editor", quiet=True)
    concise = update.render_plan(artifact)
    detailed = update.render_plan(artifact, True)
    assert "No independent verification" in concise
    assert "No independent verification" in detailed
    assert "Source request" in detailed
    assert "Current:" not in concise
    assert len(mocked_ai) == 1
    assert artifact["planning"]["timing"]["cached"] is True
    assert "DO_NOT_KEEP" not in json.dumps(artifact)


def test_save_load_unique_and_integrity(tmp_path, context, mocked_ai):
    artifact = update.research(context, "editor", quiet=True)
    first = update.save_plan(artifact, tmp_path)
    second = update.save_plan(artifact, tmp_path)
    assert first != second
    assert first.suffix == ".plan"
    assert update.load_plan(first) == artifact
    altered = json.loads(first.read_text())
    altered["plan"]["changes"][0]["proposed"] = "Wrong"
    first.write_text(json.dumps(altered))
    with pytest.raises(update.PlanError, match="changed or damaged"):
        update.load_plan(first)


def test_generate_requires_approval_and_retains_raw(tmp_path, context, mocked_ai):
    artifact = update.research(context, "editor", quiet=True)
    with pytest.raises(update.PlanError, match="approval"):
        update.generate(artifact, quiet=True)
    assert len(mocked_ai) == 1
    report, raw = update.generate(artifact, approved=True, quiet=True, recovery_dir=tmp_path)
    assert len(mocked_ai) == 2
    assert report["fact"] == []
    assert report["title"] == "Pilot"
    assert "| Done | 8 |" in report["markdown"]
    assert report["text"] != "OLD TEXT"
    assert Path(raw["recovery_path"]).suffix == ".attempt"
    assert Path(raw["recovery_path"]).exists()
    assert "DO_NOT_KEEP" not in Path(raw["recovery_path"]).read_text()


def test_blocking_questions_and_empty_plan_prevent_call(context, mocked_ai, tmp_path):
    artifact = update.research(context, "editor", quiet=True)
    artifact["plan"]["questions"] = ["Which version?"]
    artifact["digest"] = update.plan_digest(artifact)
    with pytest.raises(update.PlanError, match="blocking"):
        update.generate(artifact, approved=True, quiet=True, recovery_dir=tmp_path)
    artifact["plan"]["questions"] = []
    artifact["plan"]["changes"] = []
    artifact["digest"] = update.plan_digest(artifact)
    with pytest.raises(update.PlanError, match="no approved changes"):
        update.generate(artifact, approved=True, quiet=True, recovery_dir=tmp_path)
    assert len(mocked_ai) == 1


def test_stale_model_rejected_before_generation(context, mocked_ai, monkeypatch, tmp_path):
    artifact = update.research(context, "editor", quiet=True)
    monkeypatch.setattr(update, "get_ai_model", lambda _: "model-2")
    with pytest.raises(update.PlanError, match="agent/model changed"):
        update.generate(artifact, approved=True, quiet=True, recovery_dir=tmp_path)
    assert len(mocked_ai) == 1


def test_oversized_context_fails_before_call(context, mocked_ai, monkeypatch):
    monkeypatch.setenv("CROSS_UPDATE_CONTEXT_TOKENS", "100")
    monkeypatch.setenv("CROSS_UPDATE_OUTPUT_TOKENS", "50")
    with pytest.raises(update.PlanError, match="too large"):
        update.research(context, "editor", quiet=True)
    assert not mocked_ai


def test_failed_output_constraint_preserves_raw(context, mocked_ai, tmp_path):
    context["constraints"] = {"min_words": 1000}
    artifact = update.research(context, "editor", quiet=True)
    with pytest.raises(update.PlanError, match="Raw response retained"):
        update.generate(artifact, approved=True, quiet=True, recovery_dir=tmp_path)
    assert len(list(tmp_path.glob("*.attempt"))) == 1


def test_progress_printed_before_each_call(context, mocked_ai, tmp_path, capsys):
    artifact = update.research(context, "editor")
    assert "Generating update plan with editor" in capsys.readouterr().out
    update.generate(artifact, approved=True, recovery_dir=tmp_path)
    assert "Generating updated report with editor" in capsys.readouterr().out


def test_stale_container_and_wrong_path_rejected(tmp_path, container, mocked_ai):
    from _report_revisions import load_snapshot
    path = tmp_path / "report.json"
    path.write_text(json.dumps(container))
    value, fingerprint = load_snapshot(path)
    context = update.build_context(value, 0, "Update.", container_path=path, fingerprint=fingerprint)
    artifact = update.research(context, "editor", quiet=True)
    assert update.validate_freshness(artifact, path) == container
    with pytest.raises(update.PlanError, match="different container"):
        update.validate_freshness(artifact, tmp_path / "other.json")
    container["story"][0]["markdown"] += "\nNew edit."
    path.write_text(json.dumps(container))
    with pytest.raises(update.PlanError, match="container changed"):
        update.generate(artifact, approved=True, quiet=True)
    assert len(mocked_ai) == 1
