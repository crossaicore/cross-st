"""Audio routing checks without model downloads, servers, or playback."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import _tts


@pytest.fixture
def speech(monkeypatch):
    for key in ("TTS_BACKEND", "TTS_VOICE", "TTS_HOST", "TTS_PORT"):
        monkeypatch.delenv(key, raising=False)
    api = SimpleNamespace(kokoro_tts_server=AsyncMock(),
                          piper_tts_server=AsyncMock(), is_server_online=Mock(return_value=True))
    monkeypatch.setitem(sys.modules, "yakyak", api)
    return api


@pytest.mark.parametrize("saved,override,expected", [
    (None, None, "af_heart"), ("heart", None, "af_heart"),
    ("af_heart", "af_bella", "af_bella"),
])
def test_kokoro_needs_no_server(speech, monkeypatch, saved, override, expected, tmp_path):
    monkeypatch.setenv("TTS_BACKEND", "kokoro")
    monkeypatch.setenv("TTS_PORT", "unused")
    if saved:
        monkeypatch.setenv("TTS_VOICE", saved)
    output = str(tmp_path / "sample.mp3")
    assert _tts.render_audio("Sample report", output, override)
    speech.kokoro_tts_server.assert_awaited_once_with("Sample report", output, "mp3", expected)
    speech.is_server_online.assert_not_called()
    speech.piper_tts_server.assert_not_called()


def test_wyoming_remains_default(speech, monkeypatch):
    monkeypatch.setenv("TTS_HOST", "localhost")
    monkeypatch.setenv("TTS_PORT", "10200")
    monkeypatch.setenv("TTS_VOICE", "en_US-ryan-medium")
    assert _tts.render_audio("Sample report", "sample.mp3")
    speech.is_server_online.assert_called_once_with("localhost", 10200)
    speech.piper_tts_server.assert_awaited_once_with(
        "localhost", 10200, "Sample report", "sample.mp3", "mp3", "en_US-ryan-medium")
    speech.kokoro_tts_server.assert_not_called()


def test_offline_wyoming_does_not_render_or_claim_success(speech, capsys):
    speech.is_server_online.return_value = False
    assert not _tts.render_audio("Sample", "sample.mp3", host="localhost", port=10200)
    speech.piper_tts_server.assert_not_called()
    output = capsys.readouterr().out
    assert "offline" in output
    assert "complete" not in output


def test_quiet_kokoro(speech, monkeypatch, capsys):
    monkeypatch.setenv("TTS_BACKEND", "kokoro")
    assert _tts.render_audio("Sample", "sample.mp3", quiet=True)
    assert capsys.readouterr().out == ""


def test_invalid_backend_rejected_before_audio(speech, monkeypatch):
    monkeypatch.setenv("TTS_BACKEND", "unknown")
    with pytest.raises(ValueError, match="TTS_BACKEND"):
        _tts.render_audio("Sample", "sample.mp3")
    speech.kokoro_tts_server.assert_not_called()
    speech.piper_tts_server.assert_not_called()


def test_missing_audio_dependency_has_install_hint(speech, monkeypatch):
    monkeypatch.setenv("TTS_BACKEND", "kokoro")
    monkeypatch.setitem(sys.modules, "yakyak", None)
    with pytest.raises(SystemExit, match="pip install"):
        _tts.render_audio("Sample", "sample.mp3")


def test_st_speak_passes_voice_override_to_kokoro(speech, monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "cross_st" / "st-speak.py"
    spec = importlib.util.spec_from_file_location("st_speak_audio_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "require_config", lambda: None)
    monkeypatch.setattr(module, "load_cross_env", lambda: None)
    monkeypatch.setenv("TTS_BACKEND", "kokoro")
    report = tmp_path / "sample report.json"
    report.write_text(json.dumps({"story": [{"spoken": "Read this report."}]}))
    monkeypatch.setattr(sys, "argv", ["st-speak", "--story", "0", "--voice", "heart", str(report)])
    module.main()
    speech.kokoro_tts_server.assert_awaited_once_with(
        "Read this report.", str(report.with_suffix(".mp3")), "mp3", "af_heart")
    speech.is_server_online.assert_not_called()
