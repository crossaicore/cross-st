"""The checking matrix is reports by agents, including same-agent updates."""
import importlib.util
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest


@pytest.fixture
def setup_matrix(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "cross_st" / "st-cross.py"
    spec = importlib.util.spec_from_file_location("st_cross_report_rows", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    agents = [f"agent{i}" for i in range(5)]
    facts = [{"make": agent, "model": "model", "counts": [1, 0, 0, 0, 0]} for agent in agents]
    container = {"_st_update": True, "data": [], "story": [
        {"make": agents[i % 5], "model": "model", "text": f"Report {i+1}.",
         "fact": facts if i < 5 else []} for i in range(6)]}
    report = tmp_path / "reports.json"
    report.write_text(json.dumps(container))
    monkeypatch.setattr(module, "require_config", lambda: None)
    monkeypatch.setattr(module, "get_ai_list", lambda: agents)
    monkeypatch.setattr(module, "get_ai_make", lambda agent: "provider" + agent[-1])
    monkeypatch.setattr(module, "get_ai_model", lambda agent: "model")
    monkeypatch.setattr(module, "_filter_agents_by_key", lambda agents: (agents, []))
    monkeypatch.setattr(module, "_stories_complete", lambda *args: True)
    monkeypatch.setattr(module.signal, "signal", lambda *args: None)
    monkeypatch.setattr(module, "_get_provider_semaphore", lambda *args: threading.Semaphore(1))
    segment_counts = []
    monkeypatch.setattr(module, "_ensure_segments", lambda path, count, **kwargs: segment_counts.append(count))
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, report, agents, calls, segment_counts


def test_default_resume_checks_only_sixth_report_with_all_five_agents(setup_matrix, monkeypatch):
    module, path, agents, calls, segment_counts = setup_matrix
    monkeypatch.setattr("sys.argv", ["st-cross", str(path), "--quiet"])
    module.main()
    assert segment_counts == [6]
    assert len(calls) == 5
    assert {command[command.index("--story") + 1] for command in calls} == {"6"}
    assert {command[command.index("--agent") + 1] for command in calls} == set(agents)


def test_dry_run_counts_rectangular_matrix_and_labels_sixth_row(setup_matrix, monkeypatch, capsys):
    module, path, agents, calls, _ = setup_matrix
    before = path.read_bytes()
    monkeypatch.setattr("sys.argv", ["st-cross", str(path), "--dry-run"])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 0
    output = capsys.readouterr().out
    assert "30 cells total" in output and "S6 agent0=5" in output
    assert "25" in output and "already complete" in output
    assert not calls and path.read_bytes() == before


def test_smaller_report_set_does_not_create_nonexistent_rows(setup_matrix, monkeypatch):
    module, path, agents, calls, _ = setup_matrix
    container = json.loads(path.read_text())
    container["story"] = [container["story"][5]]
    path.write_text(json.dumps(container))
    monkeypatch.setattr("sys.argv", ["st-cross", str(path), "--skip-gen", "--quiet"])
    module.main()
    assert len(calls) == 5
    assert {command[command.index("--story") + 1] for command in calls} == {"1"}


def test_complete_six_report_matrix_does_not_launch_any_cells(setup_matrix, monkeypatch, capsys):
    module, path, agents, calls, _ = setup_matrix
    container = json.loads(path.read_text())
    container["story"][5]["fact"] = container["story"][0]["fact"]
    path.write_text(json.dumps(container))
    monkeypatch.setattr("sys.argv", ["st-cross", str(path)])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 0
    assert "6×5" in capsys.readouterr().out
    assert not calls


def test_force_checks_every_physical_report(setup_matrix, monkeypatch):
    module, path, agents, calls, _ = setup_matrix
    monkeypatch.setattr("sys.argv", ["st-cross", str(path), "--force", "--quiet"])
    module.main()
    assert len(calls) == 30
    assert {command[command.index("--story") + 1] for command in calls} == {str(i) for i in range(1, 7)}
    assert all("--no-cache" in command for command in calls)
    assert all(not report["fact"] for report in json.loads(path.read_text())["story"])


def test_force_dry_run_preserves_container(setup_matrix, monkeypatch, capsys):
    module, path, agents, calls, segment_counts = setup_matrix
    before = path.read_bytes()
    monkeypatch.setattr("sys.argv", ["st-cross", str(path), "--force", "--dry-run"])
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 0
    assert "30 cells total" in capsys.readouterr().out
    assert not calls and not segment_counts and path.read_bytes() == before


def test_generation_completeness_accepts_configured_agent_names(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "cross_st" / "st-cross.py"
    spec = importlib.util.spec_from_file_location("st_cross_names", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import cross_ai_core.agents
    monkeypatch.setattr(cross_ai_core.agents, "resolve_agent", lambda agent: SimpleNamespace(make="provider", model="model"))
    report = tmp_path / "reports.json"
    report.write_text(json.dumps({"story": [{"make": "configured-agent", "model": "model"}] * 2}))
    assert module._stories_complete(str(report), ["configured-agent"])
