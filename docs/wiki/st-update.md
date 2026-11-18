# st-update — Review and apply report updates

`st-update` revises an existing report while keeping previous versions and their
fact checks in the same JSON container. Available in the next release.

The workflow is **describe → research → review → approve → generate**. Research
analyzes your supplied material; it does not fetch new information from the web.
Fact-checking is optional.

## Your first update, step by step

You need an **existing `.json` report container**. This command updates a report
already in that file. To create an initial report, start with [st-new](st-new)
and [st-gen](st-gen).

Suppose `pilot.json` contains a pilot report and you have received new results.
Start with:

```bash
st-update pilot.json --update-details
```

1. **Choose the report.** Cross uses the active report. If there is more than one
   candidate, it asks you to choose. You can select an existing report index with
   `-s N`. The selected starting report is called the **alpha**.
2. **Describe the update.** Your configured editor opens a new update-request
   file. Write what should change, including any new facts you already have.
   Save and close the editor. For example:

   ```text
   The new pilot log reports 12 completed tasks and 3 failed tasks.
   These replace the earlier counts; do not add the old and new totals.
   Update the Findings section and recommend reviewing the failures.
   Keep the current headings, tone, and other observations.
   ```

3. **Read the proposed changes.** The AI analyzes that request and the selected
   report. Cross displays a plan describing the intended edits, reasons, source
   references, and uncertainty. At this point the report file is unchanged.
4. **Choose an action.** Type `Approve` to generate the report, `Summary` or
   `Details` to switch views, `Revise` to edit your request and get a new plan,
   or `Cancel` to stop. Pressing Enter alone does not approve.
5. **Read the new version.** After approval, Cross generates and saves a new
   report in **the same `pilot.json` file** and makes it the active report.
   The earlier version and its checks remain in that file.

   ```bash
   st-cat --markdown pilot.json
   st-update pilot.json --history
   ```

For a container with one initial report, the first update becomes v2, based on
v1. Run `st-update pilot.json` again to update v2. You do not need to create a new
container or feed every earlier prompt back into the AI.

The concise proposed summary is the default. `--update-details` chooses a more
thorough review; it does not authorize changes by itself.

## What do I put in each input file?

Your request can be a few sentences. It is **instructions for this update**,
not a replacement report and not a request to regenerate the original report.
You can supply it from a file instead of typing it in the editor:

```bash
st-update pilot.json --prompt changes.prompt --evidence new-pilot-log.md
```

This still waits for interactive approval after displaying the plan.

| Input | What it contains | When you need it |
|---|---|---|
| `pilot.json` | Existing report, prior versions, and any checks | Always |
| `changes.prompt` via `--prompt` | What to change and what to preserve | Optional alternative to the editor |
| `new-pilot-log.md` via `--evidence` | Source material supporting the changes | Optional; repeat the flag for multiple text/Markdown files |
| `--brief FILE` | Lasting purpose, audience, and scope requirements | Optional; carried into later updates |
| `--base-prompt FILE` | Missing intent behind the starting report | Optional; an absent original prompt does not block updates |

Cross uses the selected report's saved Markdown, including human edits, and its
associated authored prompt when identifiable. It asks the AI to preserve the
current wording and format outside the approved edits. Old versions stay in
history rather than being automatically included in each AI request.

**“Research” currently means analyzing your supplied material.** The command
does not search the web or obtain new figures from a date alone. Put the new
information in your request or attach it as evidence. Use separate import tools
to turn sources into local text/Markdown first when needed.

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
