# st-update — Review and apply report updates

`st-update` revises an existing report while keeping previous versions and their
fact checks in the same JSON container. Available in the next release.

The workflow is **describe → research → review → approve → generate**. Research
analyzes your supplied material; it does not fetch new information from the web.
Fact-checking is optional.

```bash
st-update research.json
st-update research.json -s 2 --prompt changes.prompt --evidence findings.md --update-details
```

The selected report is the **alpha** for this update. Its saved Markdown,
including your manual edits, supplies the starting content and formatting.
The earlier authored prompt supplies context when available. Other versions
are retained in history rather than automatically sent to the AI.

## Review before applying

`--update-summary` shows the concise proposed update summary and is the default.
`--update-details` shows individual changes, the sections affected, reasons,
source references, and uncertainty. Both views display the same plan. Switching
views does not make another AI call.

Choose **Approve**, **Details**, **Summary**, **Revise request**, or **Cancel**.
Enter alone does not approve. Revising your request produces a new plan for
review. Unresolved questions must be addressed before applying. The usual path
uses one planning call and one report-generation call after approval. Revising
the plan adds planning calls. Actual cost depends on your agent and inputs.

Approval records the intended changes. Inspect the generated report: a plan
cannot guarantee factual truth or exact obedience by the model.

## Save a plan and apply it later

```bash
st-update research.json --prompt changes.prompt --evidence findings.md \
  --update-details --review-only
# Review the plan shown above and retained at the printed path.
st-update research.json --apply-plan PATH_TO_SAVED_PLAN
```

`--review-only` makes the planning call, prints a summary, and saves an artifact
outside normal report discovery. It does not change the report container.
`--apply-plan` explicitly approves that exact artifact. Changed inputs or a
changed container require a new review. Reapplying a committed plan does not
create another revision. Non-interactive use requires this two-command flow.

Plan and recovery artifacts retain source material and model responses locally.
Keep them while reviewing or recovering an attempt; after a successful commit,
the approved plan is retained with the revision and its temporary artifacts may
be removed. Drafts use unique names and never overwrite the original prompt.

## Options

| Option | Meaning |
|---|---|
| `-s N`, `--story N` | Select the existing one-based report index, including a historical report. |
| `--agent NAME` | Configured agent for planning and generation; defaults to your default agent. |
| `--prompt FILE` | Read a UTF-8 change request without opening the editor. |
| `--brief FILE` | Supply persistent purpose, audience, and constraints carried into later updates. |
| `--base-prompt FILE` | Supply missing baseline intent. |
| `--evidence FILE` | Supply local UTF-8 text/Markdown; repeat for multiple files. |
| `--with-facts` | Include existing baseline findings as context; does not run checks. |
| `--as-of YYYY-MM-DD` | Declare temporal scope; does not fetch current evidence. |
| `--update-summary` | Concise review (default). |
| `--update-details` | Detailed review; mutually exclusive with `--update-summary`. |
| `--review-only` | Research and save a plan without generating a report. |
| `--apply-plan FILE` | Approve and apply a saved plan without repeating research. |
| `--recover-attempt FILE` | Save a retained generated response after a preparation/write failure without another AI call; validates the saved plan and current inputs. |
| `--dry-run` | Validate inputs and show expected calls without an editor, AI calls, or writes; requires `--prompt`. |
| `--draft-only` | Save an editable request without research or report changes. |
| `--check` | Cross-check only the new report after saving. |
| `--history` | Show stored report versions, indices, and revision IDs. |
| `--activate REVISION_ID` | Set the working version without generating a report. |
| `--no-spell` | Skip optional Aspell in the editor. |
| `--no-cache` | Bypass AI cache; does not refresh evidence. |
| `-q`, `--quiet` | Hide progress while retaining review and approval. |
| `-v`, `--verbose` | Additional operational details. |

Execution modes are mutually exclusive. Saved-plan application uses its stored
inputs; it rejects changes to the baseline, agent, request, evidence, or date.
Use `--check` when applying, not with `--review-only` or `--draft-only`.

Input size is checked locally without truncating evidence. The initial ceiling is
32,768 tokens with an 8,192-token output reserve, using UTF-8 bytes as a conservative
input estimate. This is a configured bound, not live model-limit discovery. For a
known model limit, configure `CROSS_UPDATE_CONTEXT_TOKENS` and
`CROSS_UPDATE_OUTPUT_TOKENS`; reduce inputs when they do not fit.

If generation succeeded but preparation or saving failed, the command retains
an `.attempt` file. `--recover-attempt PATH` explicitly approves preparing and
saving that response without a new generation call. The original plan, artifact
integrity, and current container are checked again. Changed inputs require a new
review; a recovery file does not override a concurrent edit.

## Versions and checking

```bash
st-update research.json --history
st-update research.json --activate REVISION_ID
st-update research.json --apply-plan PATH_TO_SAVED_PLAN --check
```

A footer such as `Report v3 · Based on v2` identifies the report and its parent.
Version numbers are local to the container. Branching from v1 can create v4
based on v1. Activation never renumbers reports. A new report starts unverified;
its parent's checks remain historical evidence and are not copied onto it.

`--check` runs after the new report is saved. If checking fails, the report
remains saved and the command prints a verification-only retry command.

## Compatibility in this implementation

Read/display, printing, posting, checking, and active-scope analysis preserve
revision selection. `st-edit` creates manual successor versions; `st-fix`
iterate/patch and `st-merge` create linked successors. Historical indices retain
their original meaning. Destructive removal, raw re-preparation, generation/import
into an already revisioned container, `st-analyze` container-writing runs,
`st-speed --ai-story`, and multi-source `st-fix` best-source/synthesize
are rejected explicitly. Create initial candidates in a separate container, or
use `st-update` for subsequent user-directed revisions.

External JSON edits that invalidate a saved content digest are rejected. Restore
the tracked file from backup and apply the edited text through `st-edit` so the
previous version can be retained. Do not manually alter revision metadata.

## Worked examples

[Three complete examples](st-update-examples) show preserving human edits,
refreshing supplied pilot data, and applying selected community feedback.

## Related commands

- [st-new](st-new): start an initial report prompt.
- [st-fact](st-fact) and [st-cross](st-cross): verify selected report content.
- [st-print](st-print): export or print a selected report.
- [Agents](Agents): configure planning and generating agents.
