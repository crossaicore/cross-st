"""
MDR-3 — tests for st-verdict markdown rendering integration.

Verifies that st-verdict exposes the `--no-render` opt-out and routes AI
prose through the shared `_markdown` helper. Behavioural rendering rules
(raw when piped, styled on a TTY, markup stripped) are covered by
tests/test_markdown.py; here we confirm the wiring is present without needing
a real fact-checked container or a live AI call.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "cross_st" / "st-verdict.py"


def _load_st_verdict():
    spec = importlib.util.spec_from_file_location("st_verdict_render", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # cross_st/ must be on sys.path for st-verdict's bare imports to resolve.
    sys.path.insert(0, str(_ROOT / "cross_st"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_markdown_helper_is_imported():
    m = _load_st_verdict()
    assert hasattr(m, "_markdown")
    # The helper API the prose path relies on must exist.
    assert callable(m._markdown.print_markdown)


@pytest.mark.slow
def test_no_render_flag_in_help():
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert "--no-render" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

