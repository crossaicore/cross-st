"""
Terminal markdown rendering helper (MDR-series).

Renders markdown answers as styled ANSI so tools like ``st-ask`` and
``st-verdict`` print cleaner, less-verbose output than raw markup, while
staying safe for pipes / redirects / CI.

Public API
----------
- ``should_render(stream=sys.stdout, cli_flag=None) -> bool``
      Smart-default decision. Precedence:
        1. explicit ``cli_flag`` (True/False) wins;
        2. ``CROSS_MARKDOWN=off`` global kill-switch (from ``~/.crossenv``);
        3. ``NO_COLOR`` env var set → off (community standard);
        4. ``stream.isatty()`` is False (piped / redirected / test capture) → off;
        5. otherwise → on.
- ``render(text) -> str``
      Return the styled-ANSI form of ``text`` (branded theme). Falls back to
      the original text unchanged if ``rich`` is unavailable and cannot be
      installed.
- ``print_markdown(text, *, render=None, stream=None) -> None``
      Decide via ``should_render`` then print rendered markdown, or the raw
      text unchanged when rendering is off.
- ``print_muted(text, *, render=None, stream=None) -> None``
      Print a de-emphasised line (Slate 400) — used for footers such as
      ``st-ask``'s ``(local lookup — …)``. Prints plain when rendering is off.

The renderer is a single native-Python dependency (``rich``), lazy-installed
on first use per the auto-install convention in AGENTS.md — it is never a
hard dependency of the base install.

Brand palette (branding/BRAND_GUIDE.md §3):
    Cobalt    #2563EB  — headings / accent / links
    Slate 200 #E5E7EB  — body text, bold
    Slate 400 #94A3B8  — muted, footers, rules, block-quotes
    Slate 900 #0F172A  — code surface
"""
import os
import sys
import subprocess

# Brand palette (see module docstring).
COBALT = "#2563EB"
SLATE_200 = "#E5E7EB"
SLATE_400 = "#94A3B8"
SLATE_900 = "#0F172A"

# Cached lazy-loaded rich objects: (Console, Markdown, Theme instance) or False
# once we've established rich is unavailable. ``None`` means "not tried yet".
_RICH = None


# ── Smart-default decision ───────────────────────────────────────────────────
def should_render(stream=None, cli_flag=None):
    """Return True if markdown should be rendered to ``stream``.

    ``cli_flag`` is the per-invocation preference: True forces on, False
    forces off, None means "use the smart default".
    """
    if stream is None:
        stream = sys.stdout

    # 1. Explicit CLI preference always wins.
    if cli_flag is not None:
        return bool(cli_flag)

    # 2. Global kill-switch in ~/.crossenv (loaded via mmd_startup.load_cross_env).
    if (os.getenv("CROSS_MARKDOWN") or "").strip().lower() in ("off", "0", "false", "no"):
        return False

    # 3. NO_COLOR community standard — any value disables colour/rendering.
    if os.getenv("NO_COLOR") is not None:
        return False

    # 4. Not a real terminal (piped, redirected, captured in tests) → raw.
    isatty = getattr(stream, "isatty", None)
    if not callable(isatty) or not isatty():
        return False

    # 5. Default: render.
    return True


# ── Lazy rich loader + branded theme ─────────────────────────────────────────
def _brand_theme(Theme):
    """Build a rich Theme mapping markdown roles onto the Cross palette."""
    return Theme(
        {
            "markdown.h1": f"bold {COBALT}",
            "markdown.h1.border": COBALT,
            "markdown.h2": f"bold {COBALT}",
            "markdown.h3": f"bold {COBALT}",
            "markdown.h4": f"bold {COBALT}",
            "markdown.h5": f"bold {COBALT}",
            "markdown.h6": f"bold {COBALT}",
            "markdown.strong": f"bold {SLATE_200}",
            "markdown.em": f"italic {SLATE_200}",
            "markdown.code": f"{COBALT} on {SLATE_900}",
            "markdown.code_block": f"{SLATE_200} on {SLATE_900}",
            "markdown.block_quote": SLATE_400,
            "markdown.hr": SLATE_400,
            "markdown.link": COBALT,
            "markdown.link_url": f"underline {COBALT}",
            "markdown.item.bullet": f"bold {COBALT}",
            "markdown.item.number": f"bold {COBALT}",
            # Custom role for muted footers / de-emphasised lines.
            "cross.muted": SLATE_400,
        }
    )


def _ensure_rich():
    """Import rich, lazy-installing it once on first use. Returns True on
    success, False if it is unavailable and cannot be installed."""
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        pass
    print(
        "  Markdown rendering not installed — installing now (one-time, ~2 MB)…",
        flush=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "rich"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Non-fatal: caller falls back to raw text.
        return False
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False


def _load_rich():
    """Return ``(Console, Markdown, theme)`` or ``None`` if rich is
    unavailable. Result is cached for the life of the process."""
    global _RICH
    if _RICH is not None:
        return _RICH or None
    if not _ensure_rich():
        _RICH = False
        return None
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.theme import Theme

    _RICH = (Console, Markdown, _brand_theme(Theme))
    return _RICH


# ── Rendering ────────────────────────────────────────────────────────────────
def render(text, *, width=None):
    """Return the styled-ANSI form of ``text``. Falls back to ``text``
    unchanged if rich is unavailable."""
    loaded = _load_rich()
    if loaded is None:
        return text
    Console, Markdown, theme = loaded
    console = Console(theme=theme, force_terminal=True, width=width, soft_wrap=False)
    with console.capture() as capture:
        console.print(Markdown(text))
    return capture.get()


def print_markdown(text, *, render=None, stream=None):
    """Print ``text`` as rendered markdown, or raw when rendering is off."""
    if stream is None:
        stream = sys.stdout
    if not should_render(stream, render):
        print(text, file=stream)
        return
    loaded = _load_rich()
    if loaded is None:
        print(text, file=stream)
        return
    Console, Markdown, theme = loaded
    console = Console(theme=theme, file=stream)
    console.print(Markdown(text))


def print_muted(text, *, render=None, stream=None):
    """Print a de-emphasised (Slate 400) line — used for footers. Prints
    plain text when rendering is off."""
    if stream is None:
        stream = sys.stdout
    if not should_render(stream, render):
        print(text, file=stream)
        return
    loaded = _load_rich()
    if loaded is None:
        print(text, file=stream)
        return
    Console, _Markdown, theme = loaded
    console = Console(theme=theme, file=stream)
    console.print(text, style="cross.muted")

