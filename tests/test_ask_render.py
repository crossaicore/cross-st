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


class SeeAlsoLinkTests(unittest.TestCase):
    """MDR-6 — the See-also / escape-hatch link blocks."""

    def setUp(self):
        self.m = _load_st_ask()

    def test_see_also_raw_is_bare_urls(self):
        # Piped/non-tty → plain bare-URL block (copy-paste friendly).
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.m._print_link_block("See also:", self.m._SEE_ALSO_LINKS, None)
        out = buf.getvalue()
        self.assertIn("See also:", out)
        self.assertIn("• Wiki: https://github.com/crossaicore/cross-st/wiki", out)
        # No OSC 8 hyperlink escape in raw mode.
        self.assertNotIn("\x1b]8;", out)

    def test_see_also_osc8_via_markdown_helper(self):
        import cross_st._markdown as md
        buf = FakeTTY()
        md.print_markdown("- Wiki: [https://github.com/crossaicore/cross-st/wiki]"
                          "(https://github.com/crossaicore/cross-st/wiki)",
                          render=True, stream=buf)
        out = buf.getvalue()
        # rich emits OSC 8 hyperlinks (ESC ] 8 ; … ; URL ST) for markdown links.
        self.assertIn("\x1b]8;", out)
        self.assertIn("crossaicore/cross-st/wiki", out)

    def test_see_also_rendered_shows_visible_url_text(self):
        # Regression (post-MDR-6): the URL must remain VISIBLE, not just a label.
        import cross_st._markdown as md
        buf = FakeTTY()
        with redirect_stdout(buf):
            self.m._print_link_block("See also:", self.m._SEE_ALSO_LINKS, True)
        # rich wraps long URLs; strip ANSI + newlines and check the host/path
        # fragments are present as visible text.
        import re
        visible = re.sub(r"\x1b\[[0-9;]*m", "", buf.getvalue())
        self.assertIn("crossai.dev", visible)
        self.assertIn("Community", visible)


if __name__ == "__main__":
    unittest.main()


