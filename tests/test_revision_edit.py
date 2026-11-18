"""Human edits retain report lineage and never reuse parent verification."""
import importlib.util
import json
from pathlib import Path

import pytest

import _report_revisions as rr

spec = importlib.util.spec_from_file_location("revision_edit", Path(__file__).parents[1] / "cross_st" / "st-edit.py")
edit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(edit)


@pytest.fixture
def tracked(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"data": [{"prompt": "For beginners"}], "story": [{"markdown": "# Title\n\nOld body.", "title": "Title", "fact": [{"report": "Checked old body."}]}]}))
    container, fingerprint = rr.load_snapshot(path)
    rr.commit_manual(path, fingerprint, 0, {"markdown": "# Title\n\nFirst manual edit.", "text": "First manual edit.", "title": "Title"})
    return path


@pytest.mark.parametrize("field,value", [
    ("markdown", "# Title\n\nNew **body**."),
    ("text", "New plain body."),
    ("title", "A revised title"),
    ("spoken", "A customized spoken version."),
])
def test_field_edit_creates_successor_and_rebuilds_derived_fields(tracked, field, value):
    before, fingerprint = rr.load_snapshot(tracked)
    after, index = edit._save_edit(tracked, before, fingerprint, 1, field, value)
    assert index == 2
    assert after["story"][:2] == before["story"]
    assert after["story"][index][field] == value
    assert after["story"][index]["fact"] == []
    assert after["story"][index]["report_version"] == 3
    assert rr.selected_indices(after) == [2]
    assert rr.effective_prompt(after, index) == "For beginners"
    if field == "markdown":
        assert after["story"][index]["text"] == "Title\n\nNew body."
    if field == "text":
        assert after["story"][index]["markdown"] == value
    assert len(after["data"]) == len(before["data"])


def test_manual_fact_edit_binds_same_report_without_new_revision(tracked):
    before, fingerprint = rr.load_snapshot(tracked)
    after, index = edit._save_edit(tracked, before, fingerprint, 0, "fact", "Human clarification.", 0)
    assert index == 0
    assert len(after["story"]) == 2
    fact = after["story"][0]["fact"][0]
    assert fact["report"] == "Human clarification."
    assert fact["report_id"] == after["story"][0]["report_id"]
    assert fact["content_sha256"] == after["story"][0]["content_sha256"]
    assert fact["manually_edited"] is True


def test_stale_editor_save_does_not_overwrite(tracked):
    before, fingerprint = rr.load_snapshot(tracked)
    rr.activate(tracked, before["revisions"][0]["id"])
    changed_bytes = tracked.read_bytes()
    with pytest.raises(rr.ConcurrentUpdateError):
        edit._save_edit(tracked, before, fingerprint, 1, "markdown", "Updated.")
    assert tracked.read_bytes() == changed_bytes


def test_empty_editor_save_leaves_report_unchanged(tracked):
    before, fingerprint = rr.load_snapshot(tracked)
    original = tracked.read_bytes()
    with pytest.raises(rr.RevisionError, match="Empty"):
        edit._save_edit(tracked, before, fingerprint, 1, "markdown", " ")
    assert tracked.read_bytes() == original


def test_attribution_rendered_once_without_entering_body_hash():
    report = {"markdown": "Body.", "text": "Body.", "attribution": "crossai.dev:metadata", "report_version": 2, "parent_report_versions": [1]}
    rendered = rr.render_report(report)
    assert rendered.count("crossai.dev:metadata") == 1
    assert rendered.index("crossai.dev:metadata") < rendered.index("Report v2")
    assert rr.report_body(report) == "Body."
    assert rr.content_digest(report) == rr.content_digest("Body.")


def test_view_only_renders_active_footer_without_writing(tracked, monkeypatch):
    import io
    from types import SimpleNamespace
    import shutil
    original = tracked.read_bytes()
    previews = []
    monkeypatch.setattr(edit, "require_config", lambda: None)
    monkeypatch.setattr(edit, "load_cross_env", lambda: None)
    monkeypatch.setattr(edit.sys, "argv", ["st-edit", str(tracked), "--view-only"])
    monkeypatch.setattr(shutil, "which", lambda _: "/bin/true")
    monkeypatch.setattr(edit.subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout="", returncode=0))

    class Preview:
        returncode = None
        stdout = io.BytesIO(b"* Running on http://127.0.0.1:45678\n")
        def poll(self):
            return None

    def launch(command, **kwargs):
        previews.append(Path(command[-2]))
        return Preview()

    monkeypatch.setattr(edit.subprocess, "Popen", launch)
    try:
        with pytest.raises(SystemExit) as outcome:
            edit.main()
        assert outcome.value.code == 0
        assert tracked.read_bytes() == original
        assert len(previews) == 1
        assert "Report v2 · Based on v1" in previews[0].read_text()
        assert "First manual edit." in previews[0].read_text()
    finally:
        for path in previews:
            path.unlink(missing_ok=True)


def test_failed_editor_retains_draft_and_original_container(tracked, monkeypatch):
    from types import SimpleNamespace
    original = tracked.read_bytes()
    drafts = []
    monkeypatch.setattr(edit, "require_config", lambda: None)
    monkeypatch.setattr(edit, "load_cross_env", lambda: None)
    monkeypatch.setattr(edit.sys, "argv", ["st-edit", str(tracked)])
    def failed(command, **kwargs):
        path = Path(command[-1])
        path.write_text("Uncommitted human edit.")
        drafts.append(path)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(edit.subprocess, "run", failed)
    try:
        with pytest.raises(SystemExit) as outcome:
            edit.main()
        assert outcome.value.code == 1
        assert tracked.read_bytes() == original
        assert drafts[0].read_text() == "Uncommitted human edit."
    finally:
        for path in drafts:
            path.unlink(missing_ok=True)
