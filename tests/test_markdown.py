"""
MDR-1 — unit tests for the shared terminal markdown helper (cross_st/_markdown.py).

Covers the smart-default resolver (TTY on/off, NO_COLOR, CROSS_MARKDOWN=off,
explicit-flag precedence), non-TTY byte-for-byte passthrough, and the branded
rich renderer producing styled output.
"""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

from cross_st import _markdown


class FakeTTY(io.StringIO):
    """A StringIO that reports itself as a terminal."""
    def isatty(self):
        return True


class ShouldRenderTests(unittest.TestCase):
    def setUp(self):
        # Neutralise env for a clean baseline each test.
        self._patch = mock.patch.dict(os.environ, {}, clear=False)
        self._patch.start()
        os.environ.pop("NO_COLOR", None)
        os.environ.pop("CROSS_MARKDOWN", None)

    def tearDown(self):
        self._patch.stop()

    def test_explicit_flag_true_wins(self):
        # Even piped (non-tty) + NO_COLOR set, an explicit True wins.
        os.environ["NO_COLOR"] = "1"
        self.assertTrue(_markdown.should_render(io.StringIO(), cli_flag=True))

    def test_explicit_flag_false_wins(self):
        self.assertFalse(_markdown.should_render(FakeTTY(), cli_flag=False))

    def test_cross_markdown_off_kill_switch(self):
        os.environ["CROSS_MARKDOWN"] = "off"
        self.assertFalse(_markdown.should_render(FakeTTY()))

    def test_no_color_disables(self):
        os.environ["NO_COLOR"] = ""  # any value, even empty, disables
        self.assertFalse(_markdown.should_render(FakeTTY()))

    def test_non_tty_is_off(self):
        self.assertFalse(_markdown.should_render(io.StringIO()))

    def test_tty_default_on(self):
        self.assertTrue(_markdown.should_render(FakeTTY()))


class PassthroughTests(unittest.TestCase):
    def test_non_tty_passthrough_is_raw(self):
        # Piped/redirected output must stay raw markdown (protects | pbcopy).
        buf = io.StringIO()
        text = "# Heading\n\n**bold** and `code` and a - bullet"
        _markdown.print_markdown(text, stream=buf)
        self.assertEqual(buf.getvalue(), text + "\n")

    def test_no_render_forces_raw_even_on_tty(self):
        buf = FakeTTY()
        text = "# Heading\n**bold**"
        _markdown.print_markdown(text, render=False, stream=buf)
        self.assertEqual(buf.getvalue(), text + "\n")

    def test_muted_passthrough_is_raw_when_off(self):
        buf = io.StringIO()
        _markdown.print_muted("(local lookup — no AI call)", stream=buf)
        self.assertEqual(buf.getvalue(), "(local lookup — no AI call)\n")


class RenderTests(unittest.TestCase):
    def test_render_emits_ansi_and_keeps_text(self):
        out = _markdown.render("# Hello world")
        self.assertIn("Hello", out)
        self.assertIn("\x1b[", out)  # ANSI escape sequences present

    def test_print_markdown_on_tty_strips_markup(self):
        buf = FakeTTY()
        _markdown.print_markdown("# Hello world", render=True, stream=buf)
        out = buf.getvalue()
        self.assertIn("Hello", out)
        # The literal '# ' heading marker should be gone once rendered.
        self.assertNotIn("# Hello", out)

    def test_brand_palette_constants(self):
        self.assertEqual(_markdown.COBALT, "#2563EB")
        self.assertEqual(_markdown.SLATE_400, "#94A3B8")


if __name__ == "__main__":
    unittest.main()

