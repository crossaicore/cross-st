# st-update — update a saved report

`st-update` uses a saved report, your update instructions, and any supplied evidence to generate an updated report. It saves the result and then shows what changed. Your original report remains available when you append an output.

```bash
st-update report.json                    # one report exists: append an update
st-update -s 1 report.json               # select the source explicitly
st-update -s 1 --iterate 2 report.json    # replace existing output 2 from source 1
st-update -s 2 --iterate 2 report.json    # use edited output 2 as its own source
```

## Select the source and output

`-s N` selects the existing source report. It is required when the container has multiple reports. Run `st-ls report.json` to inspect the current indices. A normal update appends a raw generation entry and prepared report; Cross prints the assigned output index.

`--iterate N` selects an existing update output to replace. Its saved update request opens in your editor so you can refine it. Both replacement entries are prepared before they are saved together. Successful iteration discards that output's previous content and raw response. Omit `--iterate` to retain them and append another output.

On the first update, a valid `--iterate N` is ignored with this message:

```text
Ignoring --iterate: no previous st-update output exists in this container.
```

Every supplied index must still exist; `--iterate` never reserves a future index. Once updates have existed, the target must have an associated update request. Removing previous updates does not reset this first-call rule. Ambiguous raw/report associations in older containers are rejected with guidance rather than guessed.

## Describe the change

Without `--prompt`, Cross opens your configured editor, followed by Aspell when available. A normal append starts with an empty request; iteration starts with the target's saved request. A supplied prompt file skips the editor:

```bash
st-update -s 1 --prompt changes.prompt --evidence observations.md --update-details report.json
```

The request and evidence files must be UTF-8. Repeat `--evidence` to include multiple files. Non-interactive use requires `--prompt FILE`. Empty requests cancel; unsuccessful editor or spell-check exits abort without saving. If generation fails after editing, Cross prints the retained request draft’s path so you can retry.

Inputs have a conservative 96,000-byte local limit. Oversized input is rejected before the AI call without dropping material; `CROSS_UPDATE_MAX_INPUT_BYTES` can override it for a model whose limits you know.

The saved source Markdown includes your manual edits. The update request takes precedence over earlier instructions; useful original intent is retained. If you manually edit output 2 and want those edits to be the next source, use `-s 2`. Using `-s 1 --iterate 2` regenerates output 2 from source 1 instead.

The command makes one AI generation call using the selected agent. It does not browse for evidence. Supplied observations and AI explanations are not independently verified.

## Review the saved result

`--update-summary` is the concise default. It shows line additions/removals computed from the actual saved Markdown and the AI's explanation of its changes. `--update-details` also shows the exact Markdown diff, along with the AI's stated reasons, sources, and uncertainties. Those reasons and source attributions are AI explanations, not verified evidence.

Read the complete report before deciding whether to keep or publish it:

```bash
st-edit --view-only --markdown -s 2 report.json
st-update -s 2 --show-summary --update-details report.json
```

`--show-summary` reads the saved summary without editing, generation, or an AI call. It requires `-s N` when multiple reports exist. If the report has been manually edited since generation, Cross explains that the summary describes the generated output. It cannot be combined with update inputs or generation options.

Review happens after the successful save. There is no separate approval command. To discard the output, use `st-rm -s 2 report.json`; its associated raw entry is removed too, and later indices shift down. Run `st-ls` again before reusing an old index. Other commands retain their existing defaults; an update does not establish a shared active report.

## Options

| Option | Purpose |
|---|---|
| `-s N`, `--story N` | Existing source index; displayed output index with `--show-summary` |
| `--iterate N` | Replace an existing update output and its raw entry |
| `--prompt FILE` | Read update instructions instead of opening the editor |
| `--evidence FILE` | Include supplied local evidence; repeatable |
| `--agent NAME` | Use a configured [agent](Agents) |
| `--update-summary` | Concise summary of the generated changes; default |
| `--update-details` | Detailed notes and exact Markdown diff |
| `--show-summary` | Redisplay a saved summary without generation |
| `--no-cache` | Bypass the AI cache; does not fetch new evidence |
| `--no-spell` | Skip optional editor spell checking |
| `-q`, `--quiet` | Suppress progress while retaining the result and summary |
| `-v`, `--verbose` | Additional diagnostics |

Generation, preparation, or concurrent-write failures leave the existing container unchanged. Updated content starts without inherited fact-checks or publication state. Run `st-fact` or `st-cross` separately when you want checking. Posting is also explicit, and local changes do not alter an existing Discourse post. Choose a distinct title before posting another report to the same site under a title already published there.

**Related:** [Worked examples](st-update-examples) · [Container format](Container-Format) · [st-edit](st-edit) · [st-rm](st-rm) · [st-fact](st-fact) · [st-post](st-post)
