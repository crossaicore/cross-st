# st-print — Print reports or save PDF

Send a saved report to a physical printer. For direct PDF export, use
**[st-pdf](st-pdf)**, which shares this command's renderer and PDF metadata.

```bash
st-print subject.json                       # print report 1 to default printer
st-print -s 2 subject.json                  # print report 2
st-print --all subject.json                 # print every report separately
st-print --printer "HP_LaserJet" subject.json
st-pdf -s 2 -o "My report.pdf" subject.json # export without printing
```

## Existing PDF options

These remain supported:

```bash
st-print --save-pdf subject.json            # save subject.pdf
st-print --output report.pdf subject.json   # save to an explicit filename
st-print --preview subject.json            # save and open; does not print
st-print --all --save-pdf subject.json      # subject_report1.pdf, etc.
```

With one exported report the automatic name is `subject.pdf`; multiple exports
use `subject_reportN.pdf` (formerly `subject_storyN.pdf`). Default output is in
the current directory. Existing files are replaced. `--output` cannot be combined
with `--all`; use one report index for a custom filename.

## Options

| Option | Purpose |
|---|---|
| `file.json` | Cross report container |
| `-s N`, `--story N` | Report index from `st-ls`, starting at 1; default 1 |
| `--all` | Print or save every report separately |
| `--save-pdf` | Save to an automatically named PDF instead of printing |
| `--output FILE.pdf` | Save to an explicit path instead of printing |
| `--preview` | Save and open the system PDF viewer instead of printing |
| `--printer NAME` | Choose a printer (`lpr -P NAME`) |
| `-v`, `--verbose` | Show rendering details |
| `-q`, `--quiet` | Suppress informational output |
| `-h`, `--help` | Show help |

Physical printing uses `lpr` on macOS/Linux and requires a configured printer.
PDF rendering uses Python-Markdown and WeasyPrint. See [st-pdf](st-pdf) for native
library setup, formatting, file naming, troubleshooting, and the Maker Matt Design
/ https://crossai.dev document properties. Neither command makes AI calls or
changes the container.

**Related:** [st-pdf](st-pdf) · [st-ls](st-ls) · [st-post](st-post) · [st-edit](st-edit)
