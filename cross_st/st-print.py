#!/usr/bin/env python3
"""
## st-print — Print reports or save PDF

Converts a report's Markdown to a high-quality PDF using WeasyPrint.
The PDF is styled with a clean, print-optimised stylesheet.

By default, sends the PDF to the system default printer via `lpr`.
Use `--save-pdf` to write to a file instead, and `--output` to specify
an explicit filename. Use `--preview` to open the PDF after saving.

Run after:  st-gen   (generated a report)
            st-prep  (polished the report text)
Run before: st-post  (publish to Discourse)
            done     (or save/print and you're finished)

```
st-print subject.json                      # print report 1 to default printer
st-print --save-pdf subject.json           # save as subject.pdf (auto-named)
st-print --output report.pdf subject.json  # save to an explicit filename
st-print -s 2 subject.json                # print report 2
st-print --all subject.json               # print all reports (one PDF each)
st-print --preview subject.json           # save PDF then open in viewer
st-print --printer "HP_LaserJet" s.json   # send to a specific printer
```

For direct PDF export, use st-pdf. Both commands share the renderer and metadata.

Options: -s N  --all  --save-pdf  --output FILE  --preview  --printer  -v  -q

Requires: pip install weasyprint
"""

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from mmd_branding import get_pdf_branding
from mmd_startup import require_config, load_cross_env

_WEASYPRINT_ERR: str | None = None
try:
    from weasyprint import HTML as _WeasyHTML
except (ImportError, OSError) as _wp_exc:
    _WeasyHTML = None  # type: ignore[assignment,misc]
    _WEASYPRINT_ERR = str(_wp_exc)

# ── Environment loading (A1 convention) ──────────────────────────────────────
load_cross_env()


# ── CSS stylesheet for printed reports ───────────────────────────────────────

_CSS = """
@page {
    size: letter;
    margin: 1in 1in 0.9in 1in;

    @bottom-center {
        content: counter(page) " / " counter(pages);
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 9pt;
        color: #888;
    }
}

/* ── Base typography ── */
body {
    font-family: Georgia, 'Times New Roman', 'Liberation Serif', serif;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a1a;
    max-width: 100%;
}

/* ── Headings ── */
h1 {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 20pt;
    font-weight: 700;
    color: #111;
    line-height: 1.25;
    margin-top: 0;
    margin-bottom: 0.4em;
    page-break-after: avoid;
}

h2 {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 14pt;
    font-weight: 700;
    color: #222;
    margin-top: 1.4em;
    margin-bottom: 0.3em;
    border-bottom: 1px solid #ddd;
    padding-bottom: 0.15em;
    page-break-after: avoid;
}

h3 {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 12pt;
    font-weight: 700;
    color: #333;
    margin-top: 1.2em;
    margin-bottom: 0.25em;
    page-break-after: avoid;
}

h4, h5, h6 {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11pt;
    font-weight: 700;
    color: #444;
    margin-top: 1em;
    margin-bottom: 0.2em;
    page-break-after: avoid;
}

/* ── Paragraphs and body content ── */
p {
    margin-top: 0;
    margin-bottom: 0.75em;
    orphans: 3;
    widows: 3;
}

/* ── Lists ── */
ul, ol {
    margin-top: 0.2em;
    margin-bottom: 0.75em;
    padding-left: 1.6em;
}

li {
    margin-bottom: 0.2em;
}

/* ── Blockquotes ── */
blockquote {
    border-left: 3px solid #aaa;
    margin-left: 0;
    padding-left: 1em;
    color: #555;
    font-style: italic;
}

/* ── Code ── */
code {
    font-family: 'Courier New', Courier, 'Lucida Console', monospace;
    font-size: 9.5pt;
    background: #f5f5f5;
    padding: 0.1em 0.3em;
    border-radius: 2px;
}

pre {
    background: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-radius: 3px;
    padding: 0.7em 0.9em;
    font-size: 9pt;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code {
    background: none;
    padding: 0;
}

/* ── Tables ── */
table {
    border-collapse: collapse;
    width: 100%;
    margin-bottom: 1em;
    font-size: 10pt;
    page-break-inside: avoid;
}

th {
    background: #f0f0f0;
    font-weight: 700;
    text-align: left;
    padding: 0.4em 0.6em;
    border: 1px solid #ccc;
}

td {
    padding: 0.35em 0.6em;
    border: 1px solid #ddd;
    vertical-align: top;
}

tr:nth-child(even) td {
    background: #fafafa;
}

/* ── Images ── */
img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0.5em auto;
}

/* ── Horizontal rule ── */
hr {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.2em 0;
}

/* ── Metadata header ── */
.story-meta {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 9pt;
    color: #666;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.5em;
    margin-bottom: 1.2em;
}

.story-meta .meta-row {
    display: inline-block;
    margin-right: 1.2em;
}

/* ── Footer branding ── */
.story-footer {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 8.5pt;
    color: #888;
    border-top: 1px solid #ddd;
    margin-top: 1.5em;
    padding-top: 0.6em;
}

/* ── Strong and emphasis ── */
strong { font-weight: 700; }
em     { font-style: italic; }
"""


# ── HTML template ─────────────────────────────────────────────────────────────

def _build_html(story: dict, story_idx: int, total_stories: int,
                source_file: str) -> str:
    """Convert a report dict to a complete HTML document for PDF rendering."""
    import markdown as md_lib

    branding = get_pdf_branding()
    make   = story.get("make", "")
    model  = story.get("model", "")
    title  = story.get("title", "").strip()
    body_md = story.get("markdown", "").strip()
    tags   = story.get("hashtags", []) or []
    date_str = datetime.today().strftime("%B %-d, %Y")

    # Convert Markdown → HTML (tables and fenced_code extensions add table/code support)
    html_body = md_lib.markdown(
        body_md,
        extensions=["extra", "tables", "fenced_code", "nl2br"],
    )

    # Build metadata row
    meta_parts = []
    if make:
        meta_parts.append(f'<span class="meta-row">AI: <strong>{_esc(make)}</strong>'
                          + (f' / {_esc(model)}' if model else '') + '</span>')
    meta_parts.append(f'<span class="meta-row">Date: {date_str}</span>')
    if total_stories > 1:
        meta_parts.append(f'<span class="meta-row">Report {story_idx} of {total_stories}</span>')
    if source_file:
        meta_parts.append(f'<span class="meta-row">Source: {_esc(os.path.basename(source_file))}</span>')

    meta_html = '<div class="story-meta">' + "".join(meta_parts) + '</div>'

    # Footer with hashtags + branding
    footer_parts = [f'<a href="{_esc(branding["website"])}">{_esc(branding["website"])}</a>']
    if tags:
        footer_parts.append(" · " + "  ".join(_esc(tag) for tag in tags))
    footer_html = f'<div class="story-footer">{" ".join(footer_parts)}</div>'

    # Title — use explicit title field; fall back to h1 extracted from markdown
    if not title:
        import re
        m = re.search(r'^#\s+(.+)$', body_md, re.MULTILINE)
        title = m.group(1).strip() if m else os.path.basename(source_file or "Report")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{_esc(title)}</title>
<meta name="author" content="{_esc(' / '.join(part for part in (make, model) if part))}">
<meta name="generator" content="{_esc(branding['creator'])}">
<meta name="description" content="{_esc(branding['subject'])}">
<meta name="dcterms.created" content="{datetime.now().astimezone().isoformat(timespec='seconds')}">
<style>{_CSS}</style>
</head>
<body>
{meta_html}
{html_body}
{footer_html}
</body>
</html>
"""


def _esc(text: str) -> str:
    """Minimal HTML entity escaping for attribute/title contexts."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ── PDF generation ────────────────────────────────────────────────────────────

def _render_pdf(html: str, base_url: str | None = None) -> bytes:
    """Render HTML to PDF bytes using WeasyPrint."""
    if _WeasyHTML is None:
        _print_weasyprint_install_hint()
        sys.exit(1)
    return _WeasyHTML(string=html, base_url=base_url).write_pdf()


def _print_weasyprint_install_hint() -> None:
    """Print a platform-appropriate WeasyPrint install hint and exit."""
    import platform
    system = platform.system()
    print()
    print("Error: PDF export requires WeasyPrint and its native Pango/GObject libraries.")
    if _WEASYPRINT_ERR:
        print(f"  Detail: {_WEASYPRINT_ERR}")
    print()
    if system == "Darwin":
        print("  Fix (macOS / Homebrew):")
        print("    brew install pango")
        print()
        print("  If WeasyPrint itself is missing from your pipx environment:")
        print("    pipx inject cross-st weasyprint")
    elif system == "Linux":
        print("  Fix (Debian/Ubuntu):")
        print("    sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0")
        print("    sudo apt-get install -y libcairo2 libgdk-pixbuf2.0-0 libffi-dev")
    else:
        print("  See: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation")
    print()


# ── Print / save helpers ──────────────────────────────────────────────────────

def _print_pdf(pdf_bytes: bytes, printer: str | None, verbose: bool) -> None:
    """Send PDF bytes to a printer via lpr (macOS / Linux)."""
    lpr_args = ["lpr"]
    if printer:
        lpr_args += ["-P", printer]

    if verbose:
        dest = printer if printer else "default printer"
        print(f"  Sending to {dest} via lpr …")

    proc = subprocess.run(
        lpr_args,
        input=pdf_bytes,
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        print(f"Error: lpr failed — {err}")
        sys.exit(1)


def _open_pdf(path: str) -> None:
    """Open a PDF file in the system viewer."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", path], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", path], check=True)
        elif system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"Could not open viewer: {e}")


def _default_pdf_path(json_file: str, story_idx: int, total: int) -> str:
    """Auto-generate a PDF filename from the container path."""
    base = Path(json_file).stem
    if total > 1:
        return f"{base}_report{story_idx}.pdf"
    return f"{base}.pdf"


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    require_config()
    parser = argparse.ArgumentParser(
        prog="st-print",
        description="Convert a report to PDF and print or save it.",
    )
    parser.add_argument(
        "json_file", type=str, metavar="file.json",
        help="Path to the report container JSON file",
    )
    parser.add_argument(
        "-s", "--story", type=int, default=1,
        help="Report number to print (1-based, default: 1)",
    )
    parser.add_argument(
        "--all", dest="all_stories", action="store_true",
        help="Print / save all reports in the container",
    )
    parser.add_argument(
        "--save-pdf", dest="save_pdf", action="store_true",
        help="Save PDF to a file instead of printing (auto-names from container)",
    )
    parser.add_argument(
        "--output", dest="output", type=str, default=None, metavar="FILE.pdf",
        help="Explicit output PDF filename (implies --save-pdf)",
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Save PDF and open it in the system PDF viewer",
    )
    parser.add_argument(
        "--printer", type=str, default=None, metavar="NAME",
        help="Send to a named printer (passed to lpr -P); default printer if omitted",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress informational output",
    )

    args = parser.parse_args(argv)
    if args.all_stories and args.output:
        parser.error("--output cannot be combined with --all; select one report with -s N")

    file_json = str(Path(args.json_file).expanduser().with_suffix(".json"))

    if not os.path.isfile(file_json):
        print(f"Error: File not found: {file_json}")
        sys.exit(1)

    try:
        with open(file_json, "r", encoding="utf-8") as f:
            container = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error: Invalid JSON in {file_json}: {e}")
        sys.exit(1)

    if not isinstance(container, dict) or not isinstance(container.get("story", []), list):
        parser.error("Expected a Cross JSON container with a report array")
    stories = container.get("story", [])
    if any(not isinstance(report, dict) for report in stories):
        parser.error("Every report in the container must be an object")
    if args.output and Path(args.output).resolve() == Path(file_json).resolve():
        parser.error("PDF output must not overwrite the source container")
    if not stories:
        print("Error: No reports found in container (run st-prep first).")
        sys.exit(1)

    # Determine which reports to process
    if args.all_stories:
        indices = list(range(1, len(stories) + 1))
    else:
        idx = args.story
        if idx < 1 or idx > len(stories):
            print(f"Error: Report {idx} does not exist (container has {len(stories)} reports).")
            sys.exit(1)
        indices = [idx]

    # Determine output mode
    do_save  = args.save_pdf or args.output or args.preview

    explicit_pdf = args.output  # str or None

    for story_idx in indices:
        story = stories[story_idx - 1]

        make  = story.get("make", "unknown")
        title_short = (story.get("title") or f"report {story_idx}")[:60]

        if not args.quiet:
            print(f"  Building PDF — report {story_idx}/{len(stories)}  [{make}]  {title_short}", flush=True)

        html = _build_html(
            story=story,
            story_idx=story_idx,
            total_stories=len(stories),
            source_file=file_json,
        )

        if args.verbose and not args.quiet:
            print("    Rendering HTML → PDF …")

        pdf_bytes = _render_pdf(html, base_url=str(Path(file_json).resolve().parent))

        if not args.quiet:
            print(f"    PDF size: {len(pdf_bytes) / 1024:.1f} KB")

        if do_save or args.preview:
            # Determine output path
            if explicit_pdf and len(indices) == 1:
                # Single report with explicit name: use it directly
                out_path = explicit_pdf
            else:
                out_path = _default_pdf_path(file_json, story_idx, len(indices))

            try:
                with open(out_path, "wb") as f:
                    f.write(pdf_bytes)
            except OSError as e:
                print(f"Error: Could not save PDF to {out_path}: {e}", file=sys.stderr)
                sys.exit(1)

            if not args.quiet:
                print(f"    Saved: {out_path}")

            if args.preview:
                _open_pdf(out_path)
        else:
            # Print mode — use a temp file (lpr reads stdin)
            _print_pdf(pdf_bytes, args.printer, args.verbose and not args.quiet)
            if not args.quiet:
                dest = f"printer '{args.printer}'" if args.printer else "default printer"
                print(f"    Sent to {dest}")


if __name__ == "__main__":
    main()

