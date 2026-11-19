# st-ls — List the contents of a story container

Lists the stories and fact-checks stored inside a `.json` container — titles, AI authors, composite quality scores, and fact-check results.

## Examples

```bash
st-ls subject.json              # default: report table (titles, quality, flags)
st-ls -a subject.json           # show all: data, stories, fact-checks, claims
st-ls --data subject.json       # raw API data items only
st-ls --fact subject.json       # fact-check summary table
st-ls -C subject.json           # cross-AI claims comparison table
st-ls --fact -C subject.json    # fact-check table + claims
```

## Options

| Option | Description |
|--------|-------------|
| `-d`, `--data` | Display raw API data items |
| `-s`, `--story` | Display the report section (titles, quality, flags) |
| `-f`, `--fact` | Display the fact-check summary table |
| `-C`, `--claims` | Display the cross-AI claims comparison table (segment × AI verdict) |
| `-c N`, `--clip N` | Clip displayed title length to N characters (default: 60) |
| `-a`, `--all` | Display all sections: data, stories, fact-checks, and claims |
| `-v`, `--verbose` | Verbose output |
| `-q`, `--quiet` | Minimal output |

**Related:** [st-cat](st-cat) · [st-edit](st-edit)

---

## For developers

List stories, data, and fact-checks inside a `.json` container.
Default shows the story table — a quick overview of all stories and their
composite quality scores, much like the Linux `ls` command gives a directory listing.
Use `-a` / `--all` to show every section, or combine flags as needed.

Run after:  st-gen   (generated your first story)
            st-bang  (generated from all AI providers)
            st-cross (ran the cross-product fact-check)
            st-fact  (ran a single fact-check)
Run before: st-print  (preview or print a story)
            st-fact   (fact-check a story)
            st-cross  (cross-check all stories)
            st-post   (publish a story)


## Story table columns

| Column | Meaning |
|--------|---------|
| S      | Story index (use with -s N in other commands) |
| Flag   | Story origin: blank = original AI output; [fix:patch/best/synth] = improved by st-fix; [merge] = synthesized by st-merge |
| Segs   | Number of fact-checkable segments extracted from the story |
| Quality | Composite score combining coverage, completeness, accuracy, and calibration; range roughly [-1, +1]. A `*` suffix marks a report excluded from best-author selection because it is incomplete. |

Quality is calculated from the available report and prompt data, even before
fact-checking. Coverage and completeness can contribute immediately; without
fact-checks, accuracy is 0 and calibration defaults to 0.5. Run `st-fact` or
`st-cross` to add fact-check evidence to the calculation. A displayed Quality value
alone does not mean the report has been fact-checked.

## See also

- st-fact   — fact-check a single story against one AI evaluator
- st-cross  — cross-product N×N fact-check (every AI checks every story)
- st-read   — display the full text of a story
- st-cat    — dump the raw JSON container

## Additional current options

- `--score-weights`: Override composite quality-score weights, e.g. "cov=0.25,comp=0.25,acc=0.40,cal=0.10". Keys: cov, comp, acc, cal (or full names).
