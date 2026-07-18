"""
tests/test_ask_telemetry.py — Unit tests for ASK-16/17 telemetry module.

Coverage:
  - is_enabled() respects CROSS_ASK_TELEMETRY env var
  - send_event() fires a background thread only when enabled
  - send_event() is fully silent on disabled / network errors
  - _maybe_prompt_telemetry_consent() writes the right value
  - st-admin --ask-telemetry on|off writes CROSS_ASK_TELEMETRY
"""
from __future__ import annotations

import importlib
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Ensure cross_st/ is importable
_CROSS_ST = str(Path(__file__).parent.parent / "cross_st")
if _CROSS_ST not in sys.path:
    sys.path.insert(0, _CROSS_ST)

import _ask_telemetry as telemetry


# ── is_enabled() ──────────────────────────────────────────────────────────────

class TestIsEnabled:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("CROSS_ASK_TELEMETRY", raising=False)
        assert telemetry.is_enabled() is False

    def test_off_when_set_to_off(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "off")
        assert telemetry.is_enabled() is False

    def test_on_when_set_to_on(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        assert telemetry.is_enabled() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "ON")
        assert telemetry.is_enabled() is True

    def test_whitespace_trimmed(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "  on  ")
        assert telemetry.is_enabled() is True

    def test_empty_string_is_off(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "")
        assert telemetry.is_enabled() is False


# ── send_event() ──────────────────────────────────────────────────────────────

class TestSendEvent:
    def test_noop_when_disabled(self, monkeypatch):
        """No thread is spawned when telemetry is off."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "off")
        with patch.object(threading, "Thread") as mock_thread:
            telemetry.send_event("hello", "pseudo", True)
        mock_thread.assert_not_called()

    def test_spawns_thread_when_enabled(self, monkeypatch):
        """A daemon thread is started when telemetry is on."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        started_threads = []

        original_thread = threading.Thread
        def capture_thread(*a, **kw):
            t = original_thread(*a, **kw)
            started_threads.append(t)
            return t

        with patch.object(threading, "Thread", side_effect=capture_thread):
            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=201)
                telemetry.send_event("how do I install", "pseudo", False)
                # give the thread a moment to run
                time.sleep(0.1)

        assert len(started_threads) == 1
        assert started_threads[0].daemon is True

    def test_posts_correct_payload(self, monkeypatch):
        """The payload includes all required fields."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        posted_payloads = []

        def fake_post(url, json=None, **kw):
            posted_payloads.append(json)
            return MagicMock(status_code=201)

        with patch("requests.post", side_effect=fake_post):
            telemetry.send_event("how do I install", "pseudo", True, agent=None)
            time.sleep(0.2)

        assert len(posted_payloads) == 1
        p = posted_payloads[0]
        assert p["query"] == "how do I install"
        assert p["tier"] == "pseudo"
        assert p["matched"] is True
        assert p["agent"] is None
        assert "cross_st_version" in p
        assert "ts" in p

    def test_llm_tier_includes_agent(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        posted = []

        with patch("requests.post", side_effect=lambda *a, **kw: (posted.append(kw.get("json", {})), MagicMock())[1]):
            telemetry.send_event("what is st-cross", "llm", True, agent="anthropic")
            time.sleep(0.2)

        assert posted[0]["agent"] == "anthropic"
        assert posted[0]["tier"] == "llm"

    def test_silent_on_network_error(self, monkeypatch):
        """A requests error must not propagate — send_event never raises."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")

        def boom(*a, **kw):
            raise ConnectionError("server unreachable")

        with patch("requests.post", side_effect=boom):
            # Must not raise
            telemetry.send_event("test query", "pseudo", False)
            time.sleep(0.2)  # wait for thread

    def test_uses_custom_url(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        monkeypatch.setenv("CROSS_ASK_TELEMETRY_URL", "http://localhost:5000/api/ask-telemetry")
        posted_urls = []

        def capture(url, **kw):
            posted_urls.append(url)
            return MagicMock(status_code=201)

        with patch("requests.post", side_effect=capture):
            telemetry.send_event("test", "pseudo", True)
            time.sleep(0.2)

        assert posted_urls[0] == "http://localhost:5000/api/ask-telemetry"


# ── _maybe_prompt_telemetry_consent() ─────────────────────────────────────────

class TestConsentPrompt:
    def _load_st_ask(self):
        spec = importlib.util.spec_from_file_location(
            "st_ask_under_test",
            Path(_CROSS_ST) / "st-ask.py",
        )
        mod = importlib.util.module_from_spec(spec)
        # Don't execute — we just want the function
        spec.loader.exec_module(mod)
        return mod

    def test_skips_when_already_on(self, monkeypatch, capsys):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        import importlib.util
        mod = self._load_st_ask()
        mod._maybe_prompt_telemetry_consent()
        out = capsys.readouterr().out
        assert out == ""

    def test_skips_when_already_off(self, monkeypatch, capsys):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "off")
        mod = self._load_st_ask()
        mod._maybe_prompt_telemetry_consent()
        out = capsys.readouterr().out
        assert out == ""

    def test_skips_when_not_a_tty(self, monkeypatch):
        monkeypatch.delenv("CROSS_ASK_TELEMETRY", raising=False)
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            # should return immediately without calling input()
            with patch("builtins.input") as mock_input:
                mod._maybe_prompt_telemetry_consent()
                mock_input.assert_not_called()

    def test_writes_on_when_user_says_y(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CROSS_ASK_TELEMETRY", raising=False)
        fake_crossenv = tmp_path / ".crossenv"
        fake_crossenv.write_text("")
        monkeypatch.setenv("HOME", str(tmp_path))

        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="y"):
                with patch("dotenv.set_key") as mock_set_key:
                    mod._maybe_prompt_telemetry_consent()
                    mock_set_key.assert_called_once()
                    args = mock_set_key.call_args[0]
                    assert args[1] == "CROSS_ASK_TELEMETRY"
                    assert args[2] == "on"

    def test_writes_off_when_user_says_n(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CROSS_ASK_TELEMETRY", raising=False)
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="n"):
                with patch("dotenv.set_key") as mock_set_key:
                    mod._maybe_prompt_telemetry_consent()
                    args = mock_set_key.call_args[0]
                    assert args[2] == "off"

    def test_writes_off_on_keyboard_interrupt(self, monkeypatch):
        monkeypatch.delenv("CROSS_ASK_TELEMETRY", raising=False)
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                with patch("dotenv.set_key") as mock_set_key:
                    mod._maybe_prompt_telemetry_consent()
                    args = mock_set_key.call_args[0]
                    assert args[2] == "off"


# ── st-admin --ask-telemetry flag ─────────────────────────────────────────────

class TestAdminAskTelemetryFlag:
    """Verify --ask-telemetry is wired into st-admin (subprocess-level checks)."""

    _ST_ADMIN = str(Path(_CROSS_ST).parent / ".venv" / "bin" / "st-admin")

    def _run(self, args):
        import subprocess
        return subprocess.run(
            [self._ST_ADMIN] + args,
            capture_output=True, text=True, timeout=15,
        )

    @pytest.fixture(autouse=True)
    def _skip_if_no_entry_point(self):
        if not Path(self._ST_ADMIN).exists():
            pytest.skip("st-admin entry point not available")

    def test_help_mentions_ask_telemetry(self):
        result = self._run(["--help"])
        assert "--ask-telemetry" in result.stdout + result.stderr

    def test_rejects_invalid_value(self):
        result = self._run(["--ask-telemetry", "maybe"])
        assert result.returncode != 0

    def test_sets_on(self, monkeypatch, tmp_path):
        """--ask-telemetry on exits 0 and prints confirmation."""
        fake_crossenv = tmp_path / ".crossenv"
        fake_crossenv.write_text("")
        import subprocess
        result = subprocess.run(
            [self._ST_ADMIN, "--ask-telemetry", "on"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "enabled" in result.stdout.lower()

    def test_sets_off(self, monkeypatch, tmp_path):
        """--ask-telemetry off exits 0 and prints confirmation."""
        fake_crossenv = tmp_path / ".crossenv"
        fake_crossenv.write_text("")
        import subprocess
        result = subprocess.run(
            [self._ST_ADMIN, "--ask-telemetry", "off"],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "disabled" in result.stdout.lower()


# ── ASK-18: helpful field in the telemetry payload ────────────────────────────

class TestHelpfulField:
    def _capture_payload(self, fn):
        """Run fn() with requests.post patched; return the single posted payload."""
        posted = []

        def fake_post(url, json=None, **kw):
            posted.append(json)
            return MagicMock(status_code=201)

        with patch("requests.post", side_effect=fake_post):
            fn()
            time.sleep(0.2)
        assert len(posted) == 1
        return posted[0]

    def test_helpful_defaults_to_none(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        p = self._capture_payload(lambda: telemetry.send_event("q", "pseudo", True))
        assert "helpful" in p
        assert p["helpful"] is None

    def test_helpful_true(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        p = self._capture_payload(
            lambda: telemetry.send_event("q", "pseudo", True, helpful=True)
        )
        assert p["helpful"] is True

    def test_helpful_false(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        p = self._capture_payload(
            lambda: telemetry.send_event("q", "llm", True, agent="a", helpful=False)
        )
        assert p["helpful"] is False


# ── ASK-18: post-answer feedback prompt (_maybe_prompt_feedback) ──────────────

class TestFeedbackPrompt:
    def _load_st_ask(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "st_ask_feedback_under_test",
            Path(_CROSS_ST) / "st-ask.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_no_prompt_when_telemetry_off(self, monkeypatch):
        """Feedback is never solicited when telemetry is disabled."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "off")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input") as mock_input:
                result = mod._maybe_prompt_feedback()
                mock_input.assert_not_called()
        assert result is None

    def test_no_prompt_when_not_a_tty(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            with patch("builtins.input") as mock_input:
                result = mod._maybe_prompt_feedback()
                mock_input.assert_not_called()
        assert result is None

    def test_no_prompt_when_feedback_disabled(self, monkeypatch):
        """--no-feedback toggles the module flag off → never prompts."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        mod._FEEDBACK_ENABLED = False
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input") as mock_input:
                result = mod._maybe_prompt_feedback()
                mock_input.assert_not_called()
        assert result is None

    def test_thumbs_up(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="y"):
                assert mod._maybe_prompt_feedback() is True

    def test_thumbs_down(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="n"):
                assert mod._maybe_prompt_feedback() is False

    def test_skip_on_enter(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value=""):
                assert mod._maybe_prompt_feedback() is None

    def test_skip_on_keyboard_interrupt(self, monkeypatch):
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                assert mod._maybe_prompt_feedback() is None

    def test_report_sends_helpful_from_prompt(self, monkeypatch):
        """_report() collects feedback and forwards it to send_event."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        sent = {}
        mod._ask_telemetry.send_event = lambda *a, **kw: sent.update(kw)
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input", return_value="y"):
                mod._report("q", tier="pseudo", matched=True)
        assert sent["helpful"] is True

    def test_report_no_feedback_for_no_match(self, monkeypatch):
        """No-match results never prompt (nothing to rate) → helpful=None."""
        monkeypatch.setenv("CROSS_ASK_TELEMETRY", "on")
        mod = self._load_st_ask()
        sent = {}
        mod._ask_telemetry.send_event = lambda *a, **kw: sent.update(kw)
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with patch("builtins.input") as mock_input:
                mod._report("q", tier="pseudo", matched=False, feedback=False)
                mock_input.assert_not_called()
        assert sent["helpful"] is None


