"""
Regression tests for the st-ask Full-LLM tier (ASK-14 / ASK-15, Phase 3).

Loads cross_st/st-ask.py by path (hyphenated filename is not importable
as a normal module) and exercises the LLM-tier helpers with a mocked
``process_prompt`` so no real API call is made.
"""
import importlib.util
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _load_st_ask():
    root = Path(__file__).resolve().parents[1]
    path = root / "cross_st" / "st-ask.py"
    spec = importlib.util.spec_from_file_location("st_ask_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SystemPromptTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()

    def test_system_prompt_wraps_corpus_with_rules(self):
        sysp = self.m._build_system_prompt()
        self.assertIsNotNone(sysp)
        # Behaviour rules present
        self.assertIn("You are st-ask", sysp)
        self.assertIn("Only reference flags", sysp)
        self.assertIn("See also:", sysp)
        # Corpus delimiters present
        self.assertIn("REFERENCE MATERIAL BEGINS", sysp)
        self.assertIn("REFERENCE MATERIAL ENDS", sysp)


class LLMAnswerTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()
        self.captured = {}

        def fake_process_prompt(agent, prompt, *, system=None, **kw):
            # ASK-14 contract: system prompt MUST be passed as a keyword.
            self.captured["agent"] = agent
            self.captured["prompt"] = prompt
            self.captured["system"] = system
            return ("payload", "client", object(), "model-x")

        self.m.ai_handler.process_prompt = fake_process_prompt
        self.m.ai_handler.get_content_auto = lambda r: "Run: pipx install cross-st"

    def test_llm_answer_passes_system_as_keyword(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._llm_answer("anthropic-sonnet", "how do I install?", "SYS")
        self.assertEqual(self.captured["system"], "SYS")
        self.assertEqual(self.captured["agent"], "anthropic-sonnet")

    def test_llm_answer_appends_see_also_block(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._llm_answer("anthropic-sonnet", "q", "SYS")
        out = buf.getvalue()
        self.assertIn("See also:", out)
        self.assertIn("crossai.dev/c/help", out)
        self.assertIn("Run: pipx install cross-st", out)

    def test_llm_answer_prints_progress_message(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._llm_answer("anthropic-sonnet", "q", "SYS")
        self.assertIn("Generating answer with anthropic-sonnet", buf.getvalue())

    def test_llm_answer_error_falls_back_gracefully(self):
        def boom(*a, **k):
            raise RuntimeError("rate limit hit")

        self.m.ai_handler.process_prompt = boom
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._llm_answer("anthropic-sonnet", "how do I install?", "SYS")
        out = buf.getvalue()
        self.assertIn("LLM error", out)
        self.assertIn("--pseudo", out)


class ExplainLastErrorTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()
        self.captured = {}

        def fake_process_prompt(agent, prompt, *, system=None, **kw):
            self.captured["prompt"] = prompt
            return ("p", "c", object(), "model")

        self.m.ai_handler.process_prompt = fake_process_prompt
        self.m.ai_handler.get_content_auto = lambda r: "explanation"

        self.path = os.path.expanduser("~/.cross_api_cache/last_error.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._backup = None
        if os.path.exists(self.path):
            with open(self.path) as f:
                self._backup = f.read()

    def tearDown(self):
        if self._backup is not None:
            with open(self.path, "w") as f:
                f.write(self._backup)
        elif os.path.exists(self.path):
            os.remove(self.path)

    def test_explain_last_error_scrubs_and_templates(self):
        with open(self.path, "w") as f:
            json.dump([{
                "ts": 1,
                "exception_type": "AuthenticationError",
                "message": "401 invalid api key sk-abc1234567890abcdef1234",
                "script": "st-fact",
            }], f)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._explain_last_error("anthropic-sonnet", "SYS")
        prompt = self.captured["prompt"]
        self.assertIn("Explain the following cross-st error", prompt)
        self.assertIn("st-fact", prompt)
        # ASK-8/ASK-15: secret must never reach the LLM.
        self.assertNotIn("sk-abc1234567890abcdef1234", prompt)
        self.assertIn("[REDACTED]", prompt)

    def test_explain_last_error_no_breadcrumb(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._explain_last_error("anthropic-sonnet", "SYS")
        self.assertIn("No recent error recorded", buf.getvalue())


class SelectAgentTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()

    def test_agent_flag_wins(self):
        class Args:
            agent = "flag-agent"
        os.environ["ASK_AGENT"] = "env-agent"
        try:
            self.assertEqual(self.m._select_agent(Args()), "flag-agent")
        finally:
            del os.environ["ASK_AGENT"]

    def test_ask_agent_env_beats_default(self):
        class Args:
            agent = None
        os.environ["ASK_AGENT"] = "env-agent"
        try:
            self.assertEqual(self.m._select_agent(Args()), "env-agent")
        finally:
            del os.environ["ASK_AGENT"]


class EnvLoadTests(unittest.TestCase):
    """Regression: main() must load ~/.crossenv before deciding the tier,
    otherwise keys stored there are invisible and st-ask wrongly falls back
    to Pseudo-AI (bug reported 2026-07-04)."""

    def setUp(self):
        self.m = _load_st_ask()

    def test_main_loads_cross_env_before_tier_decision(self):
        import builtins
        called = {"v": False}

        def fake_load():
            called["v"] = True

        def eof_input(*a, **k):
            raise EOFError

        self.m.mmd_startup.load_cross_env = fake_load
        old_argv, old_input = sys.argv, builtins.input
        sys.argv = ["st-ask", "--pseudo"]   # pseudo REPL; EOF exits at once
        builtins.input = eof_input
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                self.m.main()
        finally:
            sys.argv, builtins.input = old_argv, old_input
        self.assertTrue(called["v"], "main() must call load_cross_env()")


if __name__ == "__main__":
    unittest.main()

