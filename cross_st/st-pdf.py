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
st-pdf -s 2 -f 1 subject.json               # fact-check 1 for report 2
st-pdf --preview subject.json               # save and open in PDF viewer
```

Options: -s/--story N  -f/--fact N  -o/--output FILE.pdf  --preview  -v  -q  -h

Files are saved in the current directory unless --output includes a directory.
Existing output files are replaced. A missing .pdf suffix is added; other
suffixes are rejected. Each call exports one report or one fact-check.
Use -s N -f M to export saved fact-check M for report N; find indices with
st-ls --story --fact subject.json. The default fact-check filename is
subject_reportN_factM.pdf. Use --output to choose your own name.

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
        description="Export a saved report or fact-check as PDF (no AI call).",
        epilog="Default: file.pdf in the current directory; existing PDFs are replaced. "
               "Fact-check default: file_reportN_factM.pdf. See st-man st-pdf.",
    )
    parser.add_argument("json_file", metavar="file.json", help="Cross report container")
    parser.add_argument("-s", "--story", type=int, default=1, metavar="N",
                        help="Report index from st-ls (1-based, default: 1)")
    parser.add_argument("-f", "--fact", type=int, metavar="N",
                        help="Export fact-check N for the selected report (1-based)")
    parser.add_argument("-o", "--output", metavar="FILE.pdf",
                        help="Output PDF filename or path; adds .pdf if no suffix")
    parser.add_argument("--preview", action="store_true", help="Save and open in the system PDF viewer")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show rendering details")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress informational output")
    args = parser.parse_args(argv)

    forwarded = ["--save-pdf", "-s", str(args.story)]
    if args.fact is not None:
        forwarded += ["-f", str(args.fact)]
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
