# st-rm — Remove reports and associated raw data

Removes a report and its associated raw-data entry from a `.json` container. Use `-s` to select the report and `-f` to remove only a fact-check. Removing a report compacts the arrays; use `st-ls` again before reusing an index. Local deletion does not remove a published post.

Raw/report associations are resolved from saved links or provable legacy content. Ambiguous legacy pairs are rejected without changing the container. `-d N` can remove an unowned raw entry; use `-s N` for a complete pair.

## Examples

```bash
st-rm -s 3 subject.json              # remove report 3
st-rm -d 2 subject.json              # remove data item 2
st-rm -s 2 -f 1 subject.json         # remove fact-check 1 from report 2
st-rm -F -s 2 subject.json           # clear all fact-checks from report 2
st-rm -F --all-stories subject.json  # clear all fact-checks from every report
```

## Options

| Option | Description |
|--------|-------------|
| `file.json` | Path to the JSON container |
| `-d N`, `--data N` | Remove a data item by index |
| `-s N`, `--story N` | Remove a report and its associated raw entry by index |
| `-f N`, `--fact N` | Remove a fact-check report from a report by index |
| `-F`, `--clear-facts` | Clear all fact-checks (and segments) from a report (`-s`) or all reports |
| `--all-stories` | Apply `--clear-facts` to every report in the container |
| `-v`, `--verbose` | Verbose output |
| `-q`, `--quiet` | Minimal output |

**Related:** [st-ls](st-ls) · [st-cat](st-cat)

---

## For developers

Deletes complete report/raw pairs, unowned data items, or fact-check records from a .json container.
Supports bulk-clearing all fact-checks and claim segments from one report or
every report in the container.


All index arguments are 1-based, matching the output of st-ls.
