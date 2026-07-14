"""
MDR-2 — tests for st-ask markdown rendering integration.

Loads cross_st/st-ask.py by path (hyphenated filename) and checks that:
  * piped/non-tty output stays raw markdown (protects `st-ask "…" | pbcopy`);
  * `--no-render` (render_pref=False) forces raw even on a faked TTY;
  * rendering on a faked TTY strips the markdown markup.
"""
import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path


def _load_st_ask():
    root = Path(__file__).resolve().parents[1]
    path = root / "cross_st" / "st-ask.py"
    spec = importlib.util.spec_from_file_location("st_ask_render_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class PseudoRenderTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()
        # A high-confidence FAQ entry so _pseudo_answer takes the answer branch.
        self.entry = {
            "id": "install",
            "question": "How do I install cross-st?",
            "answer": "# Install\n\nRun `pipx install cross-st` to get started.",
        }

    def test_answer_piped_stays_raw_markdown(self):
        # Non-tty stream (redirect_stdout to StringIO) → raw markdown out.
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._print_answer(self.entry)
        out = buf.getvalue()
        self.assertIn("# Install", out)          # heading marker intact
        self.assertIn("`pipx install cross-st`", out)  # backticks intact
        # Footer present and unstyled.
        self.assertIn(self.m.FOOTER, out)

    def test_answer_rendered_on_tty_strips_markup(self):
        import cross_st._markdown as md
        buf = FakeTTY()
        md.print_markdown(self.entry["answer"], render=True, stream=buf)
        out = buf.getvalue()
        self.assertIn("pipx install cross-st", out)
        self.assertNotIn("# Install", out)  # heading rendered, marker gone

    def test_no_render_pref_raw_via_helper(self):
        import cross_st._markdown as md
        buf = FakeTTY()
        md.print_markdown(self.entry["answer"], render=False, stream=buf)
        self.assertEqual(buf.getvalue(), self.entry["answer"] + "\n")


class LLMRenderTests(unittest.TestCase):
    def setUp(self):
        self.m = _load_st_ask()

        def fake_process_prompt(agent, prompt, *, system=None, **kw):
            return ("payload", "client", object(), "model-x")

        self.m.ai_handler.process_prompt = fake_process_prompt
        self.m.ai_handler.get_content_auto = lambda r: "# Answer\n\nRun `pipx install cross-st`."

    def test_llm_answer_piped_stays_raw(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._llm_answer("anthropic-sonnet", "how?", "SYS")
        out = buf.getvalue()
        self.assertIn("# Answer", out)
        self.assertIn("`pipx install cross-st`", out)
        self.assertIn("See also:", out)


if __name__ == "__main__":
    unittest.main()


