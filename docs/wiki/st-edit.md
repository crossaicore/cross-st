# st-edit — Edit or view report fields in a container

Opens any field in a report container — report text, title, spoken version, or a fact-check — in your configured editor. Changes are saved to the selected report in the `.json` file; manual editing does not append an output. Markdown/text edits rebuild derived fields and clear stale checks/segments. Title changes also clear checks. Publication and export pointers are cleared when their content changes; existing remote posts and exported files remain independent. Concurrent changes abort the save rather than overwrite newer work.

**Run after:** `st-prep`

---

## Examples

```bash
st-edit subject.json                    # edit report 1 markdown in $EDITOR
st-edit -s 2 subject.json              # edit report 2
st-edit --markdown subject.json        # edit the markdown field of report 1
st-edit --title subject.json           # edit the title field
st-edit --text subject.json            # edit the plain-text field
st-edit --spoken subject.json          # edit the spoken-audio source text
st-edit -f 1 subject.json             # edit fact-check report 1
st-edit --view subject.json            # view report in the browser with Grip, then open editor
st-edit --view-only subject.json       # view report in the browser with Grip (read-only)
```

## Options

| Option | Description |
|--------|-------------|
| `file.json` | Path to the JSON container |
| `-s N`, `--story N` | Report to edit (1-based index, default: 1) |
| `-f N`, `--fact N` | Fact-check report to edit (1-based index) |
| `-md`, `--markdown` | Edit the Markdown field |
| `-title`, `--title` | Edit the title field |
| `-text`, `--text` | Edit the plain-text field |
| `-spoken`, `--spoken` | Edit the text-to-speech source text |
| `--view` | View with Grip in the browser first, then open editor |
| `--view-only` | View with Grip in the browser only — no editing |
| `-q`, `--quiet` | Minimal output |
| `-v`, `--verbose` | Verbose output |

**Related:** [st-update](st-update)  [st-prep](st-prep)  [st-fix](st-fix)  [st-admin](st-admin)

---

## For developers

Reads the targeted field from the `story[]` array, writes it to a temp file, opens `$EDITOR`, then writes the saved content back. For `--fact`, reads from `fact[].summary` or the full fact report JSON.
