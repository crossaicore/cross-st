#!/usr/bin/env python3
"""
## st-pdf — Export reports as PDF

Save a report from a Cross JSON container as a formatted PDF. Uses the same
renderer as st-print. Reads the saved Markdown; makes no AI calls and leaves
the container unchanged. Report indices match st-ls (1-based, default: 1).

```
st-pdf subject.json                         # save subject.pdf
st-pdf -s 2 subject.json                    # export report 2 to subject.pdf
st-pdf -s 2 -o "My report.pdf" subject.json  # choose a filename or path
st-pdf --all subject.json                   # subject_report1.pdf, etc.
st-pdf --preview subject.json               # save and open in PDF viewer
```

Options: -s/--story N  --all  -o/--output FILE.pdf  --preview  -v  -q  -h

Files are saved in the current directory unless --output includes a directory.
Existing output files are replaced. --output selects one filename and cannot
be combined with --all. A missing .pdf suffix is added; other suffixes are
rejected. --all exports separate PDFs, with numbered names for multiple reports.

PDF properties include the report title, AI provider/model when recorded,
and Cross / Maker Matt Design / https://crossai.dev export metadata.
The formatting supports headings, lists, tables, links, and images.

Requires WeasyPrint and native Pango/GObject libraries (macOS: brew install pango).
Use st-print for a physical printer. Learn more: st-man st-pdf --web.
"""

import argparse
from pathlib import Path
import runpy

from mmd_startup import require_config


def main(argv=None):
    require_config()
    parser = argparse.ArgumentParser(
        prog="st-pdf",
        description="Export a saved report as PDF (no AI call).",
        epilog="Default: file.pdf in the current directory; existing PDFs are replaced. "
               "Use --all for separate file_reportN.pdf exports. See st-man st-pdf.",
    )
    parser.add_argument("json_file", metavar="file.json", help="Cross report container")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("-s", "--story", type=int, default=1, metavar="N",
                           help="Report index from st-ls (1-based, default: 1)")
    selection.add_argument("--all", action="store_true", help="Export every report as a separate PDF")
    parser.add_argument("-o", "--output", metavar="FILE.pdf",
                        help="Output filename or path for one report; adds .pdf if no suffix")
    parser.add_argument("--preview", action="store_true", help="Save and open in the system PDF viewer")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show rendering details")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args(argv)
    if args.all and args.output:
        parser.error("--output cannot be combined with --all; export one report with -s N")

    forwarded = ["--save-pdf"]
    forwarded += ["--all"] if args.all else ["-s", str(args.story)]
    if args.output:
        output = Path(args.output).expanduser()
        if not output.suffix:
            output = output.with_suffix(".pdf")
        elif output.suffix.lower() != ".pdf":
            parser.error("--output must name a .pdf file (or omit the suffix)")
        forwarded += ["--output", str(output)]
    for flag in ("preview", "verbose", "quiet"):
        if getattr(args, flag):
            forwarded.append("--" + flag)
    forwarded += ["--", args.json_file]
    # Load the existing command without invoking its __main__ block. Keeping the
    # renderer in one place gives both commands identical PDF output.
    print_command = runpy.run_path(str(Path(__file__).with_name("st-print.py")))
    print_command["main"](forwarded)


if __name__ == "__main__":
    main()
