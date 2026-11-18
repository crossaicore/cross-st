"""Complete-pair writes, conservative associations and removal semantics."""
from copy import deepcopy
import importlib.util
import json
import multiprocessing
from pathlib import Path
from types import SimpleNamespace

import pytest

import _report_store as store


def _competing_update(path, fingerprint, start, results):
    start.wait(10)
    try:
        store.commit_update(path, fingerprint, 0, {}, {"markdown": "Concurrent result"}, "Request")
        results.put("saved")
    except store.ConcurrentWriteError:
        results.put("stale")


def module(name):
    path = Path(__file__).parents[1] / "cross_st" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


@pytest.fixture
def report_path(tmp_path):
    path = tmp_path / "report with spaces.json"
    path.write_text(json.dumps({"extra": {"keep": True}, "data": [{"prompt": "Original intent", "model": "old", "make": "writer"}],
        "story": [{"title": "Original", "markdown": "Human-edited source.", "fact": [{"score": 1.5}]}]}))
    return path


def update(path, target=None, source=0, request="Add current facts"):
    _, fingerprint = store.load_snapshot(path)
    return store.commit_update(path, fingerprint, source,
        {"make": "writer", "model": "new", "gen_response": {"content": "fresh"}, "base_prompt": "Original intent"},
        {"make": "writer", "model": "new", "markdown": "New report.", "text": "New report.", "fact": [{"old": True}], "topic_id": 99, "segments": ["stale"]},
        request, summary={"summary": "Added current facts"}, target_index=target)


def test_append_keeps_prior_entries_and_links_new_pair(report_path):
    before, _ = store.load_snapshot(report_path)
    after, index = update(report_path)
    assert index == 1
    assert {k: v for k, v in after["story"][0].items() if k not in ("source_data_id", "authored_prompt")} == before["story"][0]
    assert {k: v for k, v in after["data"][0].items() if k != "data_id"} == before["data"][0]
    assert store.raw_index(after, 0) == 0
    assert store.authored_prompt(after, 0) == "Original intent"
    assert after["extra"] == before["extra"]
    assert after["story"][1]["source_data_id"] == after["data"][1]["data_id"]
    assert store.raw_index(after, 1) == 1
    assert store.update_request(after, 1) == "Add current facts"
    assert store.authored_prompt(after, 1) == "Add current facts"
    assert after["story"][1]["fact"] == []
    assert after["story"][1]["_generated_by"] == "st-update"
    assert "topic_id" not in after["story"][1]
    assert "segments" not in after["story"][1]
    assert store.has_updates(after)
    assert set(after) == {"data", "story", "extra", "_st_update"}


def test_iterate_same_source_replaces_entire_pair_at_same_positions(report_path):
    before, _ = update(report_path)
    before["data"][1]["discard_me"] = True
    before["story"][1]["discard_me"] = True
    report_path.write_text(json.dumps(before))
    after, index = update(report_path, target=1, source=1, request="Refine current facts")
    assert index == 1
    assert len(after["data"]) == len(after["story"]) == 2
    assert after["data"][0] == before["data"][0]
    assert after["story"][0] == before["story"][0]
    assert "discard_me" not in after["data"][1]
    assert "discard_me" not in after["story"][1]
    assert after["data"][1]["data_id"] == before["data"][1]["data_id"]
    assert after["story"][1]["source_data_id"] == before["story"][1]["source_data_id"]
    assert store.update_request(after, 1) == "Refine current facts"


def test_reordered_raw_entries_are_replaced_by_link_not_array_position(report_path):
    before, _ = update(report_path)
    before["data"].reverse()
    report_path.write_text(json.dumps(before))
    after, _ = update(report_path, target=1)
    assert store.raw_index(after, 1) == 0
    assert after["data"][1] == before["data"][1]


def test_legacy_shared_model_is_never_used_to_guess_pairs(report_path):
    before, _ = store.load_snapshot(report_path)
    before["story"].append(deepcopy(before["story"][0]))
    before["data"].append(deepcopy(before["data"][0]))
    assert store.raw_index(before, 0) is None
    assert store.authored_prompt(before, 0) == "Original intent"
    before["data"][1]["prompt"] = "A different intent"
    assert store.authored_prompt(before, 0) is None
    with pytest.raises(store.StoreError, match="safely"):
        store.remove_pair(before, 0)
    assert len(before["story"]) == 2


def test_legacy_multiple_reports_match_exact_prepared_body_not_positions():
    from mmd_branding import get_tagline_for_reading
    raws = [{"make": "url", "model": "file", "markdown": f"# Report {i}\n\nUnique body {i}."} for i in range(5)]
    reports = [{"markdown": raw["markdown"] + "\n\n" + get_tagline_for_reading("url", "file")} for raw in raws]
    container = {"data": list(reversed(raws)), "story": reports}
    assert store.raw_index(container, 1) == 3
    after = store.remove_pair(container, 1)
    assert len(after["data"]) == len(after["story"]) == 4
    assert raws[1] not in after["data"]
    assert reports[1] not in after["story"]


def test_legacy_provider_response_matching_is_local_and_unique(monkeypatch):
    import ai_handler
    monkeypatch.setattr(ai_handler, "get_content_auto", lambda response: response["content"])
    container = {"data": [
        {"make": "writer", "gen_response": {"_make": "provider", "content": "First body"}},
        {"make": "writer", "gen_response": {"_make": "provider", "content": "Second body"}}],
        "story": [{"markdown": "Second body"}, {"markdown": "First body"}]}
    assert store.raw_index(container, 0) == 1
    container["story"][0]["text"] = "Second body"
    container["story"][0]["markdown"] = "Human edited body"
    assert store.raw_index(container, 0) is None
    container["story"][0]["markdown"] = "Second body"
    container["data"].append(deepcopy(container["data"][1]))
    assert store.raw_index(container, 0) is None


def test_original_sole_pair_remains_removable_after_append(report_path):
    after, _ = update(report_path)
    new_pair_id = after["data"][1]["data_id"]
    after = store.remove_report(report_path, 0)
    assert len(after["data"]) == len(after["story"]) == 1
    assert after["data"][0]["data_id"] == new_pair_id
    assert store.raw_index(after, 0) == 0


def test_append_preserves_common_legacy_authored_intent(report_path):
    before, _ = store.load_snapshot(report_path)
    before["data"] *= 5
    before["story"] *= 5
    report_path.write_text(json.dumps(before))
    after, index = update(report_path)
    assert index == 5
    assert all(store.authored_prompt(after, i) == "Original intent" for i in range(5))
    assert store.authored_prompt(after, 5) == "Add current facts"
    assert all("_generated_by" not in report for report in after["story"][:5])


def test_sole_legacy_pair_can_be_resolved_and_removed(report_path):
    before, _ = store.load_snapshot(report_path)
    assert store.raw_index(before, 0) == 0
    assert store.authored_prompt(before, 0) == "Original intent"
    after = store.remove_report(report_path, 0)
    assert after["data"] == after["story"] == []
    assert after["extra"] == before["extra"]


def test_remove_pair_compacts_arrays_and_retains_update_marker(report_path):
    update(report_path)
    after, _ = update(report_path)
    removed_id = after["data"][1]["data_id"]
    remaining_id = after["data"][2]["data_id"]
    after = store.remove_report(report_path, 1)
    assert len(after["story"]) == len(after["data"]) == 2
    assert store.raw_index(after, 1) == 1
    assert after["data"][1]["data_id"] == remaining_id
    assert not any(raw.get("data_id") == removed_id for raw in after["data"])
    after = store.remove_report(report_path, 1)
    assert store.has_updates(after) and after["_st_update"] is True
    assert len(after["story"]) == 1


def test_deleting_last_update_preserves_detection_even_without_prior_marker(report_path):
    after, _ = update(report_path)
    del after["_st_update"]
    report_path.write_text(json.dumps(after))
    after = store.remove_report(report_path, 1)
    assert store.has_updates(after)


def test_shared_explicit_raw_reference_is_not_removed(report_path):
    after, _ = update(report_path)
    after["story"].append(deepcopy(after["story"][1]))
    report_path.write_text(json.dumps(after))
    original = report_path.read_bytes()
    with pytest.raises(store.StoreError, match="share"):
        store.remove_report(report_path, 1)
    with pytest.raises(store.StoreError, match="share"):
        update(report_path, target=1)
    assert report_path.read_bytes() == original


def test_failed_replace_and_stale_snapshot_leave_pair_intact(report_path, monkeypatch):
    update(report_path)
    original = report_path.read_bytes()
    _, fingerprint = store.load_snapshot(report_path)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(store.os, "replace", fail)
    with pytest.raises(OSError, match="disk full"):
        update(report_path, target=1)
    assert report_path.read_bytes() == original
    report_path.write_bytes(original + b"\n")
    changed = report_path.read_bytes()
    with pytest.raises(store.ConcurrentWriteError):
        store.commit_update(report_path, fingerprint, 0, {}, {"markdown": "new"}, "request", target_index=1)
    assert report_path.read_bytes() == changed


def test_invalid_indices_and_experimental_metadata_do_not_mutate(report_path):
    before, fingerprint = store.load_snapshot(report_path)
    for index in (-1, 2, True):
        with pytest.raises(store.StoreError):
            store.commit_update(report_path, fingerprint, index, {}, {"markdown": "new"}, "request")
    before["revision_schema_version"] = 1
    report_path.write_text(json.dumps(before))
    original = report_path.read_bytes()
    with pytest.raises(store.StoreError, match="st-fetch --file"):
        store.load_snapshot(report_path)
    assert report_path.read_bytes() == original


def test_data_id_is_assigned_once_and_validated():
    raw = {}
    first = store.ensure_data_id(raw)
    assert first and store.ensure_data_id(raw) == first
    with pytest.raises(store.StoreError):
        store.ensure_data_id({"data_id": None})


def test_concurrent_processes_commit_only_one_complete_pair(report_path):
    _, fingerprint = store.load_snapshot(report_path)
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    workers = [context.Process(target=_competing_update, args=(str(report_path), fingerprint, start, results)) for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        start.set()
        assert sorted(results.get(timeout=15) for _ in workers) == ["saved", "stale"]
        for worker in workers:
            worker.join(10)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
        results.close()
    after, _ = store.load_snapshot(report_path)
    assert len(after["data"]) == len(after["story"]) == 2
    assert store.raw_index(after, 1) == 1
    assert len({raw["data_id"] for raw in after["data"]}) == 2


def test_new_prepared_report_does_not_share_deduplicated_raw_pair():
    raw = {"data_id": "existing", "gen_response": {"content": "Body"}}
    container = {"data": [raw], "story": [{"source_data_id": "existing", "markdown": "Prior prepared body"}]}
    report = {"markdown": "New prepared body"}
    index = store.link_new_report(container, raw, report)
    container["story"].append(report)
    assert index == 1
    assert report["source_data_id"] != "existing"
    assert container["data"][index]["gen_response"] == raw["gen_response"]
    after = store.remove_pair(container, 1)
    assert after == {"data": [raw], "story": [container["story"][0]]}


def test_new_report_respects_implicit_legacy_raw_ownership():
    raw = {"markdown": "Existing body"}
    old = {"markdown": "Existing body"}
    container = {"data": [raw], "story": [old]}
    new = {"markdown": "New prepared body"}
    assert store.link_new_report(container, raw, new) == 1
    container["story"].append(new)
    assert store.raw_index(container, 0) == 0
    assert store.raw_index(container, 1) == 1
    assert store.remove_pair(container, 0)["story"] == [new]


def test_append_captures_all_legacy_links_before_equal_content_is_added(tmp_path):
    container = {"data": [{"markdown": "First"}, {"markdown": "Second"}],
                 "story": [{"markdown": "First"}, {"markdown": "Second"}]}
    path = tmp_path / "same.json"
    path.write_text(json.dumps(container))
    _, fingerprint = store.load_snapshot(path)
    after, _ = store.commit_update(path, fingerprint, 0, {"markdown": "First"},
                                    {"markdown": "First"}, "Keep wording")
    assert [store.raw_index(after, i) for i in range(3)] == [0, 1, 2]
    remaining = store.remove_pair(after, 0)
    assert len(remaining["data"]) == len(remaining["story"]) == 2


def test_st_prep_links_imported_raw_and_preserves_edits_on_repeat(tmp_path, monkeypatch):
    prep = module("st-prep")
    path = tmp_path / "import.json"
    path.write_text(json.dumps({"data": [{"make": "url", "model": "file", "markdown": "# Imported\n\nRaw body."}], "story": []}))
    monkeypatch.setattr(prep, "load_cross_env", lambda: None)
    monkeypatch.setattr(prep, "require_config", lambda: None)
    monkeypatch.setattr(prep.sys, "argv", ["st-prep", str(path), "--quiet"])
    prep.main()
    first, _ = store.load_snapshot(path)
    assert store.raw_index(first, 0) == 0
    first["story"][0]["markdown"] = "# Imported\n\nHuman edits."
    first["story"][0]["fact"] = [{"score": 2}]
    path.write_text(json.dumps(first))
    prep.main()
    second, _ = store.load_snapshot(path)
    assert second == first


@pytest.mark.parametrize("saved_title", [None, "", "  ", 123, "Green Bean Casserole"])
def test_st_prep_title_does_not_absorb_single_spaced_body(tmp_path, monkeypatch, capsys, saved_title):
    prep = module("st-prep")
    path = tmp_path / "import.json"
    body = "# Green Bean Casserole\nFood\nA report with several lines.\n" + "More content. " * 30
    path.write_text(json.dumps({"data": [{"make": "st-fetch", "model": "file",
        "title": saved_title, "markdown": body}], "story": []}))
    monkeypatch.setattr(prep, "load_cross_env", lambda: None)
    monkeypatch.setattr(prep, "require_config", lambda: None)
    monkeypatch.setattr(prep.sys, "argv", ["st-prep", str(path), "--title"])
    prep.main()
    saved, _ = store.load_snapshot(path)
    assert saved["story"][0]["title"] == "Green Bean Casserole"
    assert path.with_suffix(".title").read_text() == "Green Bean Casserole"
    assert "More content." in saved["story"][0]["markdown"]
    assert "Title very long" not in capsys.readouterr().out


def test_fetch_url_title_survives_preparation(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    import requests

    pytest.importorskip("bs4")
    fetch = module("st-fetch")
    prep = module("st-prep")
    html = """<html><head><title>Green Bean Casserole - Food - Shangri-La</title></head>
    <body><h1>Green Bean Casserole</h1><p>Food</p><p>Author and date</p>
    <p>A report with ingredients and cooking directions.</p></body></html>"""
    monkeypatch.setattr(requests, "get", lambda *a, **kw: SimpleNamespace(
        text=html, status_code=200, raise_for_status=lambda: None))
    for command in (fetch, prep):
        monkeypatch.setattr(command, "load_cross_env", lambda: None)
        monkeypatch.setattr(command, "require_config", lambda: None)
    path = tmp_path / "green-bean-casserole.json"

    def run_prep(argv, **kwargs):
        assert argv[:3] == ["st-prep", "-d", "1"]
        with monkeypatch.context() as context:
            context.setattr(prep.sys, "argv", argv)
            prep.main()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(fetch.subprocess, "run", run_prep)
    monkeypatch.setattr(fetch.sys, "argv", ["st-fetch", "--url",
        "https://example.test/t/green-bean-casserole/494", str(path)])
    fetch.main()
    saved, _ = store.load_snapshot(path)
    assert saved["data"][0]["title"] == "Green Bean Casserole"
    assert saved["story"][0]["title"] == "Green Bean Casserole"
    assert store.raw_index(saved, 0) == 0
    assert "ingredients" in saved["story"][0]["markdown"]
    assert "Title very long" not in capsys.readouterr().out

    # Re-preparing must preserve an authored title and existing fact checks.
    saved["story"][0]["title"] = "My edited casserole report"
    saved["story"][0]["fact"] = [{"score": 2}]
    path.write_text(json.dumps(saved))
    monkeypatch.setattr(prep.sys, "argv", ["st-prep", str(path), "--title"])
    prep.main()
    assert store.load_snapshot(path)[0] == saved
    assert path.with_suffix(".title").read_text() == "My edited casserole report"
    assert "Title: My edited casserole report" in capsys.readouterr().out


def test_st_prep_update_uses_clean_markdown_not_response_json(tmp_path, monkeypatch):
    prep = module("st-prep")
    path = tmp_path / "update.json"
    path.write_text(json.dumps({"data": [{"make": "writer", "model": "model", "_generated_by": "st-update",
        "markdown": "# Report\n\nClean body.", "gen_response": {"body": '{"markdown":"report","changes":[]}'}}], "story": []}))
    monkeypatch.setattr(prep, "load_cross_env", lambda: None)
    monkeypatch.setattr(prep, "require_config", lambda: None)
    monkeypatch.setattr(prep, "get_ai_list", lambda: ["writer"])
    monkeypatch.setattr(prep, "get_data_content", lambda *_: pytest.fail("Provider JSON must not become report body"))
    monkeypatch.setattr(prep.sys, "argv", ["st-prep", str(path), "--quiet"])
    prep.main()
    after, _ = store.load_snapshot(path)
    assert after["story"][0]["markdown"].startswith("# Report\n\nClean body.")
    assert "changes" not in after["story"][0]["markdown"]


def test_st_rm_removes_linked_pair_and_keeps_marker(report_path, monkeypatch):
    remove = module("st-rm")
    update(report_path)
    monkeypatch.setattr(remove, "require_config", lambda: None)
    monkeypatch.setattr(remove.sys, "argv", ["st-rm", "-s", "2", str(report_path), "--quiet"])
    remove.main()
    after, _ = store.load_snapshot(report_path)
    assert len(after["data"]) == len(after["story"]) == 1
    assert store.has_updates(after)


def test_st_rm_raw_only_refuses_dangling_report(report_path, monkeypatch):
    remove = module("st-rm")
    update(report_path)
    original = report_path.read_bytes()
    monkeypatch.setattr(remove, "require_config", lambda: None)
    monkeypatch.setattr(remove.sys, "argv", ["st-rm", "-d", "2", str(report_path)])
    with pytest.raises(SystemExit):
        remove.main()
    assert report_path.read_bytes() == original


def test_fix_saves_independent_pairs_and_rebuilds_derived_content(report_path):
    fix = module("st-fix")
    container, _ = store.load_snapshot(report_path)
    original = container["story"][0]
    original["spoken"] = "Stale speech"
    original["hashtags"] = ["#stale"]
    report_path.write_text(json.dumps(container))
    args = SimpleNamespace(agent="writer", mode="iterate", story=1, fact=1, quiet=True, prep=False)
    fix._save_result(container, str(report_path), args, "writer", "model", "model",
                     "# Revised\n\nFresh body.", {}, "", original)
    after, _ = store.load_snapshot(report_path)
    assert store.raw_index(after, 1) == 1
    assert "Fresh body" in after["story"][1]["spoken"]
    assert "Stale speech" not in after["story"][1]["spoken"]
    assert after["story"][1]["fact"] == []
    # Same response with a different prepared title must not share a raw pair.
    changed_title = dict(original, title="Another title")
    fix._save_result(after, str(report_path), args, "writer", "model", "model",
                     "# Revised\n\nFresh body.", {}, "", changed_title)
    saved, _ = store.load_snapshot(report_path)
    assert store.raw_index(saved, 2) == 2
    assert saved["story"][1]["source_data_id"] != saved["story"][2]["source_data_id"]
