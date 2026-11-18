"""Remaining report producers preserve complete pairs and report scope."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import _report_store as store


def module(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"),
        Path(__file__).parents[1] / "cross_st" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_cached_generation_dedup_requires_same_prompt_model_and_content():
    prior = {"make": "writer", "model": "model", "prompt": "Original question",
             "gen_response": {"content": "Original answer"}, "data_id": "old",
             "timing": {"cached": False, "elapsed_seconds": 30}, "md5_hash": "old"}
    cached = deepcopy(prior)
    cached.update(data_id="new", md5_hash="new", timing={"cached": True})
    assert store.same_generation(prior, cached)
    for key, value in (("prompt", "Different question"), ("model", "Other model"),
                       ("gen_response", {"content": "New answer"})):
        changed = dict(cached, **{key: value})
        assert not store.same_generation(prior, changed)


def test_speed_generation_saves_actual_response_in_complete_pair(tmp_path, monkeypatch):
    speed = module("st-speed")
    path = tmp_path / "speed.json"
    original = {"data": [], "story": []}
    path.write_text(json.dumps(original))
    record = {}
    response = {"content": "A measured 10 seconds."}
    calls = []
    def generate(*args, **kwargs):
        calls.append(args)
        return {"prompt": "actual payload"}, None, response, "actual-model"
    monkeypatch.setattr(speed, "process_prompt", generate)
    monkeypatch.setattr(speed, "get_content_auto", lambda value: value["content"])
    monkeypatch.setattr(speed, "validate_ai_content", lambda *args: (True, 5, None))
    monkeypatch.setattr(speed, "build_ai_prompt", lambda *args: "Performance request")
    text = speed.generate_ai_content([{"AI": "writer"}], [], "writer", "story", generation_record=record)
    assert speed.save_story_to_container(original, path, text, "writer", record["model"], [], [], raw_data=record) == 1
    saved, _ = store.load_snapshot(path)
    assert len(calls) == 1
    assert store.raw_index(saved, 0) == 0
    assert saved["data"][0]["gen_response"] == response
    assert saved["data"][0]["gen_payload"] == {"prompt": "actual payload"}
    assert saved["story"][0]["model"] == "actual-model"


def test_speed_stale_snapshot_does_not_save_half_pair(tmp_path):
    speed = module("st-speed")
    path = tmp_path / "speed.json"
    original = {"data": [], "story": []}
    path.write_text(json.dumps(original))
    _, fingerprint = store.load_snapshot(path)
    path.write_text(json.dumps(dict(original, changed=True)))
    before = path.read_bytes()
    assert speed.save_story_to_container(original, path, "New report", "writer", "model", [], [],
                                         expected_fingerprint=fingerprint) == -1
    assert path.read_bytes() == before
    assert original == {"data": [], "story": []}


def test_analysis_preserves_per_report_requirements_and_saves_pair(tmp_path, monkeypatch):
    analyze = module("st-analyze")
    path = tmp_path / "analysis with spaces.json"
    original = {"data": [], "story": [
        {"title": "Original", "markdown": "Original content", "authored_prompt": "Use 2024 evidence"},
        {"title": "Updated", "markdown": "Updated content", "authored_prompt": "Use supplied 2026 evidence"}]}
    path.write_text(json.dumps(original))
    monkeypatch.setattr(analyze, "require_config", lambda: None)
    monkeypatch.setattr(analyze, "load_cross_env", lambda: None)
    monkeypatch.setattr(analyze, "get_discourse_slugs_sites", lambda: ([], []))
    monkeypatch.setattr(analyze, "get_ai_list", lambda: ["writer"])
    monkeypatch.setattr(analyze, "get_default_ai", lambda: "writer")
    monkeypatch.setattr(analyze, "get_ai_model", lambda *_: "configured-model")
    monkeypatch.setattr(analyze, "get_flattened_fc_data", lambda *_: [{"score": 1}, {"score": 2}])
    monkeypatch.setattr(analyze.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="{}", stderr=""))
    monkeypatch.setattr(analyze, "post_plot", lambda *_: {})
    monkeypatch.setattr(analyze, "get_content_auto", lambda *_: "# Analysis\n\nTwo separate reports.")
    prompts = []
    def generate(agent, prompt, **kwargs):
        prompts.append(prompt)
        return {"prompt": prompt}, None, {"content": "Analysis"}, "actual-model"
    monkeypatch.setattr(analyze, "process_prompt", generate)
    monkeypatch.setattr(analyze.sys, "argv", ["st-analyze", str(path), "--quiet"])
    analyze.main()
    saved, _ = store.load_snapshot(path)
    assert store.raw_index(saved, 2) == 0
    assert "### S1: Original\nUse 2024 evidence" in prompts[0]
    assert "### S2: Updated\nUse supplied 2026 evidence" in prompts[0]
    assert "This prompt was used for each AI under study" not in prompts[0]
    assert saved["story"][2]["model"] == "actual-model"


@pytest.mark.parametrize("bad", [{"story": "not an array"}, {"revision_schema_version": 1}])
def test_speed_rejects_bad_container_early(tmp_path, bad):
    speed = module("st-speed")
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad))
    assert speed.load_container(path) is None
