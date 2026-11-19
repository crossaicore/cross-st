# st-pdf — Export reports as PDF

**Save a formatted PDF with one command:**

```bash
st-pdf subject.json
```

This reads report 1 from `subject.json` and saves `subject.pdf` in your current
working directory. It uses the saved Markdown, including manual edits and updates.
It makes no AI calls and leaves the JSON container unchanged.

## Choose the report and filename

Use the same report indices shown by `st-ls` and accepted by other commands:

```bash
st-ls subject.json
st-pdf -s 2 subject.json
st-pdf -s 2 -o "My finished report.pdf" subject.json
st-pdf -s 2 --output ~/Documents/summary.pdf --preview subject.json
```

`--preview` saves the PDF and opens your system PDF viewer. It does not print.
The destination directory must already exist. Quote paths containing spaces.
If the output has no suffix, `.pdf` is added; other suffixes are rejected.

**Existing output files are replaced.** Without `--output`, exporting a different
report from the same container replaces `subject.pdf`. Choose a separate filename
to keep each export, or export all reports at once.

## Export all reports

```bash
st-pdf --all subject.json
```

For a container with three reports, this writes `subject_report1.pdf`,
`subject_report2.pdf`, and `subject_report3.pdf` in the current directory.
A container with only one report produces `subject.pdf`.
Each file contains one report; this command does not merge reports into a book.

`--all` cannot be combined with `-s` or `--output`. Export one report at a time
with `-s N --output FILE.pdf` when you want individual custom names.

## Options

| Option | Purpose |
|---|---|
| `file.json` | Cross JSON container to read |
| `-s N`, `--story N` | Report index, starting at 1; defaults to 1 |
| `--all` | Export every report to a separate PDF |
| `-o FILE.pdf`, `--output FILE.pdf` | Choose one output filename or path |
| `--preview` | Save and open in the system PDF viewer |
| `-v`, `--verbose` | Show rendering details |
| `-q`, `--quiet` | Suppress informational output; errors still appear |
| `-h`, `--help` | Show command help |

The long selector spelling `--story` is retained for consistency with existing
Cross commands. It selects a report, just like `-s`.

## Formatting and PDF properties

The shared `st-print` renderer supports headings, emphasis, lists, blockquotes,
tables, code blocks, clickable links, and images. Pages use Letter size, readable
body text, a report/source header, a website footer, and page numbers. Relative
image paths resolve from the directory containing the JSON file; remote images
need network access. Rendering arbitrary Markdown/HTML is not a guarantee of
pixel-identical reproduction of its original website.

The PDF's document properties include:

| Property | Value |
|---|---|
| Title | Saved report title, falling back to its first heading or container filename |
| Author | Recorded AI make and model, when present |
| Creator | `Cross — Maker Matt Design` |
| Subject | `Exported with Cross by Maker Matt Design — https://crossai.dev` |
| Creation date | Time of export |
| Producer | WeasyPrint (the rendering software) |

Maker Matt Design is credited as the software maker. The report's AI attribution
remains separate. Metadata is not a fact-check, certification, or copyright claim.
Both `st-pdf` and `st-print` embed these properties.

## In the interactive app

Open `st subject.json`, select a report with `S`, then open **Post** (`p`):

- `d` saves the selected report with `st-pdf -s N`.
- `D` sends it to the default printer with `st-print -s N`.

Use `st-pdf -o ...` directly when you want a custom filename.

## Setup and troubleshooting

WeasyPrint is included with Cross. Its native Pango/GObject libraries must also
be available. On macOS, install them with `brew install pango`; on Debian/Ubuntu,
use `sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0`.
The command prints platform-specific setup guidance if the renderer cannot load.

- **No reports found:** use `st-ls file.json` to inspect the container. If it has
  raw responses only, prepare them with `st-prep file.json`.
- **Report does not exist:** choose an existing index from `st-ls`.
- **Could not save PDF:** check that the destination directory exists and is writable.
- **Missing image:** check the image path or URL; remote resources may be unavailable.

## Learn more

```bash
st-pdf --help
st-man st-pdf
st-man st-pdf --web
st-ask "How do I export a report as PDF?"
```

For physical printing use [st-print](st-print). Its existing `--save-pdf`,
`--output`, and `--preview` options remain supported. Batch exports from either
command now use `_reportN.pdf` filenames (previously `_storyN.pdf` in `st-print`).

Related: [st-ls](st-ls) · [st-update](st-update) · [st-post](st-post) · [st](st)
