"""Revision integrity, reviewed-plan replay, and file transaction regressions."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

import _report_revisions as rr


@pytest.fixture
def legacy():
    return {"private_extension": {"keep": True}, "data": [{"prompt": "Original intent", "make": "fixture", "timing": {"elapsed": 2}}],
            "story": [{"title": "Human title", "markdown": "# Human heading\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nHuman closing note.",
                       "text": "Original plain text.", "fact": [{"score": 9}], "custom": "keep"}]}


@pytest.fixture
def path(tmp_path, legacy):
    target = tmp_path / "report with spaces.json"
    target.write_text(json.dumps(legacy))
    return target


def update(path, text="# Updated\n\nNew facts.", plan_id="plan-1", parent=0):
    _, fingerprint = rr.load_snapshot(path)
    return rr.commit_update(path, fingerprint, parent,
        {"markdown": text, "text": "New facts.", "title": "Human title", "fact": [{"stale": True}], "topic_id": 123},
        {"prompt": "assembled input", "gen_response": {"text": text}},
        {"id": plan_id, "digest": plan_id + "-digest", "context": {"request": "Add facts", "standing_brief": "For beginners"}},
        {"method": "interactive", "at": "2026-11-17", "plan_id": plan_id, "plan_digest": plan_id + "-digest"})


def test_adoption_preserves_all_existing_fields_and_facts(path, legacy):
    after, index = update(path)
    assert index == 1
    assert after["private_extension"] == legacy["private_extension"]
    for key, value in legacy["story"][0].items():
        assert after["story"][0][key] == value
    assert after["data"][0]["timing"] == legacy["data"][0]["timing"]
    assert after["story"][1]["fact"] == []
    assert "topic_id" not in after["story"][1]
    assert after["revisions"][0]["created_at"] is None
    assert after["story"][0]["source_data_id"] is None
    assert rr.selected_indices(after) == [1]
    assert rr.selected_indices(after, 1) == [0]
    assert rr.effective_prompt(after, 0) == "Original intent"
    assert rr.effective_prompt(after, 1) == "Add facts"
    assert rr.effective_brief(after, 1) == "For beginners"


def test_branching_and_activation_do_not_renumber(path):
    update(path)
    update(path, plan_id="plan-2", parent=1)
    after, index = update(path, plan_id="plan-3", parent=0)
    assert index == 3
    assert rr.version_label(after["story"][3]) == "Report v4 · Based on v1"
    original = after["revisions"][0]["id"]
    active = rr.activate(path, original)
    assert rr.selected_indices(active) == [0]
    assert active["next_report_version"] == 5
    assert [x["report_version"] for x in active["story"]] == [1, 2, 3, 4]


def test_replay_before_stale_fingerprint_check(path):
    _, original = rr.load_snapshot(path)
    after, _ = update(path)
    result, index = rr.commit_update(path, original, 0, {}, {}, {"id": "plan-1", "digest": "plan-1-digest"}, {"method": "saved", "plan_id": "plan-1", "plan_digest": "plan-1-digest"})
    assert index == 1 and result == after
    with pytest.raises(rr.RevisionError, match="different plan"):
        rr.commit_update(path, original, 0, {}, {}, {"id": "plan-1", "digest": "changed"}, {"method": "saved", "plan_id": "plan-1", "plan_digest": "changed"})


def test_stale_snapshot_preserves_concurrent_changes(path):
    before, fingerprint = rr.load_snapshot(path)
    before["extension"] = "concurrent"
    path.write_text(json.dumps(before))
    content = path.read_bytes()
    with pytest.raises(rr.ConcurrentUpdateError):
        rr.commit_update(path, fingerprint, 0, {"markdown": "New."}, {}, {"id": "p", "digest": "d"}, {"method": "saved", "plan_id": "p", "plan_digest": "d"})
    assert path.read_bytes() == content


def test_empty_output_and_missing_approval_leave_legacy_untouched(path):
    _, fingerprint = rr.load_snapshot(path)
    original = path.read_bytes()
    with pytest.raises(rr.RevisionError, match="approval"):
        rr.commit_update(path, fingerprint, 0, {"markdown": "New."}, {}, {"id": "p", "digest": "d"}, {})
    with pytest.raises(rr.RevisionError, match="Empty"):
        rr.commit_update(path, fingerprint, 0, {"markdown": " "}, {}, {"id": "p", "digest": "d"}, {"method": "saved", "plan_id": "p", "plan_digest": "d"})
    assert path.read_bytes() == original


def test_failed_atomic_replace_leaves_original_valid(path, monkeypatch):
    original = path.read_bytes()
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(rr.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        update(path)
    assert path.read_bytes() == original
    assert not list(path.parent.glob("*.tmp"))


def test_atomic_fact_write_preserves_history(path):
    update(path)
    container, fingerprint = rr.load_snapshot(path)
    prior = deepcopy(container["story"][0]["fact"])
    report = container["story"][1]
    report["fact"].append({"score": 10, "report_id": report["report_id"], "content_sha256": report["content_sha256"]})
    rr.atomic_write(path, container, fingerprint)
    after, _ = rr.load_snapshot(path)
    assert after["story"][0]["fact"] == prior
    assert after["story"][1]["fact"][0]["score"] == 10


def test_atomic_write_cannot_rewrite_history_even_with_new_digest(path):
    update(path)
    container, fingerprint = rr.load_snapshot(path)
    container["story"][0]["markdown"] = "Changed old body."
    container["story"][0]["content_sha256"] = rr.content_digest(container["story"][0])
    with pytest.raises(rr.RevisionError, match="immutable"):
        rr.atomic_write(path, container, fingerprint)


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(revision_schema_version=2),
    lambda c: c.update(active_revision_id="missing"),
    lambda c: c.update(next_report_version=1),
    lambda c: c["story"][0].update(markdown="external edit"),
    lambda c: c["story"][1].update(report_version=1),
    lambda c: c["story"][1].update(source_data_id="missing"),
    lambda c: c["revisions"][1].update(parent_report_ids=[c["story"][1]["report_id"]]),
    lambda c: c["revisions"][1].update(report_ids=[]),
])
def test_invalid_revision_states_rejected(path, mutate):
    container, _ = update(path)
    mutate(container)
    with pytest.raises(rr.RevisionError):
        rr.validate_container(container)


def test_managed_footer_idempotent_and_human_version_text_survives():
    report = {"markdown": "Human says Report v7.\n\nA closing note.", "report_version": 2, "parent_report_versions": [1]}
    rendered = rr.render_report(report)
    assert rendered.count("Report v2") == 1
    assert rr.report_body({"markdown": rendered}) == report["markdown"]
    assert rr.render_report({**report, "markdown": rendered}) == rendered
    assert rr.content_digest({"markdown": rendered}) == rr.content_digest(report)
    assert "Human says Report v7." in rendered
    assert rr.render_report(report, "text").endswith("Report v2 · Based on v1")


def test_canonical_digest_excludes_timing_facts_and_normalizes_lines():
    assert rr.content_digest("e\u0301\r\nBody.\r\n") == rr.content_digest("é\nBody.")
    assert rr.content_digest({"markdown": "Body.", "fact": [1], "timing": 123}) == rr.content_digest("Body.")


def test_ambiguous_legacy_prompt_is_not_guessed(legacy):
    legacy["data"].append({"prompt": "Another intent"})
    assert rr.effective_prompt(legacy, 0) is None
    assert rr.effective_prompt({"story": [{"markdown": "Imported."}]}, 0) is None


def test_legacy_selection_retains_physical_indices(legacy):
    legacy["story"].append({"markdown": "Second."})
    assert rr.selected_indices(legacy) == [0, 1]
    assert rr.selected_indices(legacy, 2) == [1]
    for index in (0, -1, 3, True):
        with pytest.raises(rr.RevisionError):
            rr.selected_indices(legacy, index)


def test_unsupported_writer_rejects_revisioned_only(path, legacy):
    rr.require_legacy_write(legacy, "st-prep")
    container, _ = update(path)
    with pytest.raises(rr.RevisionError, match="st-prep"):
        rr.require_legacy_write(container, "st-prep")


def test_approval_is_bound_to_the_reviewed_plan(path):
    _, fingerprint = rr.load_snapshot(path)
    original = path.read_bytes()
    with pytest.raises(rr.RevisionError, match="exact reviewed"):
        rr.commit_update(path, fingerprint, 0, {"markdown": "New."}, {},
            {"id": "p", "digest": "d"}, {"method": "saved", "plan_id": "another", "plan_digest": "d"})
    assert path.read_bytes() == original


def test_legacy_writer_cannot_overwrite_concurrent_adoption(path, legacy):
    update(path)
    original = path.read_bytes()
    with pytest.raises(rr.RevisionError, match="does not yet support"):
        rr.save_legacy(path, legacy)
    assert path.read_bytes() == original


def test_merge_successor_retains_multiple_parent_labels(path):
    update(path)
    container, fingerprint = rr.load_snapshot(path)
    after, index = rr.commit_successor(path, fingerprint, [0, 1],
        {"markdown": "Merged.", "title": "Merged"}, {"prompt": "Merge these reports"},
        kind="merge", change_request="Compare both")
    assert index == 2
    assert rr.version_label(after["story"][index]) == "Report v3 · Based on v1, v2"
    assert rr.effective_prompt(after, index) == "Compare both"
    assert after["story"][:2] == container["story"]


def test_commit_cannot_substitute_a_different_plan_parent(path):
    _, fingerprint = rr.load_snapshot(path)
    with pytest.raises(rr.RevisionError, match="parent does not match"):
        rr.commit_update(path, fingerprint, 0, {"markdown": "New."}, {},
            {"id": "p", "digest": "d", "context": {"parent_index": 1}},
            {"method": "saved", "plan_id": "p", "plan_digest": "d"})


def _concurrent_commit_worker(path, fingerprint, plan_id, barrier, results):
    """Spawn-safe process entry: both writers begin from the same reviewed file."""
    import _report_revisions as revisions
    try:
        barrier.wait(timeout=10)
        container, index = revisions.commit_update(path, fingerprint, 0,
            {"markdown": f"New content from {plan_id}."}, {"prompt": plan_id},
            {"id": plan_id, "digest": plan_id + "-digest"},
            {"method": "saved", "plan_id": plan_id, "plan_digest": plan_id + "-digest"})
        results.put(("saved", index))
    except revisions.ConcurrentUpdateError:
        results.put(("stale", None))
    except Exception as exc:
        results.put(("error", repr(exc)))


def test_two_processes_cannot_commit_the_same_snapshot(path):
    import multiprocessing
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(2), context.Queue()
    _, fingerprint = rr.load_snapshot(path)
    processes = [context.Process(target=_concurrent_commit_worker,
        args=(str(path), fingerprint, f"plan-{i}", barrier, results)) for i in range(2)]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert sorted(outcome[0] for outcome in outcomes) == ["saved", "stale"]
        container, _ = rr.load_snapshot(path)
        assert len(container["story"]) == 2
        assert len({r["report_id"] for r in container["story"]}) == 2
        assert [r["report_version"] for r in container["story"]] == [1, 2]
        assert container["next_report_version"] == 3
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
