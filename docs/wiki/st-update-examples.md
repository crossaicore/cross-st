# st-update — three worked examples

> All organizations, prices, measurements, comments, and results below are fictional teaching inputs. No generation, checking, or publishing commands were run to produce this document.

## How to read the examples

Each example creates one initial report, then appends two updated reports in the same container. The labels **report 1**, **report 2**, and **report 3** refer to command indices, not permanent content versions or text added to the report. Normal Cross attribution remains.

The reports and semantic change summaries below are illustrative teaching examples; actual summaries include deterministic Markdown line counts and AI explanations. Use `--show-summary -s N` to read a saved summary again without generating another output.

The sequence is **create → generate → list → inspect/edit → optionally post → update → review the saved result**. `st-update` opens the request editor, generates and saves the output, and prints a change summary. `--update-summary` is the concise default; `--update-details` provides more detail. Review includes the full saved report; no separate plan approval is required.

`-s N` selects the source and is required whenever multiple reports exist. A normal update appends an output and prints its assigned index. `--iterate N` instead reopens an existing output's update prompt and replaces that output using the selected source. Source and output may be the same report. Replacement is prepared in temporary entries and saved only on success. See the [selection and first-call rules](st-update#select-the-source-and-output).

The full reports below follow the append path. Iteration and removal commands are alternative next actions; do not run every command as a batch. After deleting an entry, later indices shift down. No active-report state is shared between commands.

Fact-checking is off in these examples. Supplied observations are not independently verified, and updates do not browse for evidence or publish automatically.

**Posting note:** `MySite` means a configured Discourse site. A published post remains independent of the local report. After posting an initial report, an update with the same title cannot be posted to that same site again . Choose a distinct posting title with `st-edit -s N --title FILE.json` before a later `st-post`. The report bodies below keep their headings consistent to make content changes easy to compare.

## Example 1: Fill gaps in a human-edited report

**Question this answers:** Can I add missing considerations without losing my own edits or the report’s formatting?

**Scenario:** A volunteer organizer compares two rooms for a workshop. The initial prompt asked for paragraphs, but the organizer replaced that section with a table and added the sentence “Keep the event welcoming and practical.” The saved, edited Markdown is the source for the first update.

The user runs `st-new workshop` to create `workshop.prompt`.

### Initial prompt

```text
Write a short report helping a volunteer organizer choose a room for a
10-person workshop. Use the headings Options and Recommendation, with
short paragraphs. Keep the tone practical and welcoming.

Supplied quotes:
- Cedar Room: $40 room hire, capacity 16.
- Main Hall: $70 room hire, capacity 24.
Choose a room on the information available. Identify missing information.
```

After creating the prompt, the user generates, lists, and edits the report:

```bash
st-gen workshop.prompt
st-ls workshop.json
st-edit -s 1 --markdown workshop.json
```

### Report 1 — initial output, including the human edits

```markdown
# Workshop venue choice

## Options

| Room | Hire | Capacity |
|---|---:|---:|
| Cedar Room | $40 | 16 |
| Main Hall | $70 | 24 |

Both rooms can accommodate the planned 10 participants. The supplied quotes cover room hire only; access arrangements and other event costs have not been confirmed.

## Recommendation

Choose Cedar Room provisionally: it accommodates the group and costs $30 less. Confirm access arrangements before booking.

Keep the event welcoming and practical.
```

The report is satisfactory, so the user posts it to Discourse:

```bash
st-post -s 1 --site MySite workshop.json
```

`workshop.json` contains one report with no fact-checks.

### First update — add the missing accessibility information

The user has learned that two participants need step-free access. The venue coordinator confirms that Cedar Room is reached only by stairs, while Main Hall has step-free access. The user wants to add this information and revise the recommendation.
The user runs `st-update workshop.json` to open the editor for the update prompt below.
The command could have been `st-update -s 1 workshop.json` to explicitly select report 1 as the source. Because it is the only report, it can be selected without `-s`. Once the container has more than one report, `-s <index>` is required; there is no highest-numbered or active-report default.

**Update prompt:**

```text
Two participants need step-free access. The venue coordinator has confirmed
that Cedar Room is reached only by stairs and Main Hall has step-free access.
Add this information and revise the recommendation. Attendance is still 10.
```

st-update submits the request to the AI with the saved Markdown from source report 1.
Cross appends report 2 and its associated raw generation entry to the same container, then prints the assigned report index.
By default, st-update prints a summary of the generated changes.
The user could have selected `--update-details` to see a detailed view of the generated changes, including the AI’s stated source for each change and any uncertainties, plus the exact Markdown diff. Source attributions are not independently verified.

From this point the user has options. If report 2 is acceptable, the user can choose a distinct posting title and publish it with `st-post -s 2 --site MySite workshop.json`. If the user wants to make further changes, they can run `st-edit -s 2 --markdown workshop.json` to edit the report.

To iterate on the report, the user has two main options:

One, repeat the process to append report 3, report 4, and so on. Creating extra reports may or may not be desirable.
The command `st-update -s 2 workshop.json` selects existing report 2 as the source and appends a new output. Cross assigns and prints the output index; the user does not supply or guess the next index.

The second option is to edit the update prompt associated with report 2 and regenerate report 2.
The command is `st-update -s 1 --iterate 2 workshop.json`: report 1 is the source, and existing report 2 holds the iterative prompt and receives the regenerated output. The previous update prompt is shown in the editor for editing. The AI then uses the source report and edited prompt to replace report 2 and prints a summary. Both indices must exist; `--iterate 2` does not allocate a new report.
The power user might use `st-edit --view-only --markdown -s 2 workshop.json` to see the rendered markdown.

To discard the saved output, the user runs `st-rm -s 2 workshop.json`. This removes report 2 and its associated raw-data entry. Later entries shift down if present; this does not remove a published post.

**Context used:** the saved report 1 Markdown, its source prompt, and this update request. No checks or earlier raw AI output are needed. The old request for paragraphs must not remove the human’s table.

**Summary after saving report 2 (illustrative):**

```text
Saved report 2 in workshop.json — based on report 1
- Added access information for both rooms to the Options table.
- Changed the recommendation to Main Hall for step-free access.
- Retained attendance, prices, headings, and the human closing sentence.
Evidence: venue coordinator information supplied in your update request.
Limitations: no independent access check; other event costs remain unknown.
View: st-edit --view-only --markdown -s 2 workshop.json
```

The detailed view would identify `U1: Options table — added Access column: Cedar Room = stairs only; Main Hall = step-free`, citing the coordinator statement, and `U2: Recommendation — changed to Main Hall`, citing the access requirement. These describe the saved report below. The user reviews that report before deciding whether to publish, edit, regenerate, continue, or discard it. No additional approval command is introduced here.

**Report 2 — updated output:**

```markdown
# Workshop venue choice

## Options

| Room | Hire | Capacity | Access |
|---|---:|---:|---|
| Cedar Room | $40 | 16 | Stairs only |
| Main Hall | $70 | 24 | Step-free |

Both rooms can accommodate the planned 10 participants, but two participants need step-free access. The venue coordinator confirms that only Main Hall meets that requirement. The quotes cover room hire only; other event costs remain unconfirmed.

## Recommendation

Choose Main Hall. Its $30 higher hire cost provides the access this group needs. Cedar Room is unsuitable for the planned participants despite its lower price.

Keep the event welcoming and practical.
```

**What changed:** an Access column and the recommendation. The title, two headings, table presentation, practical tone, and human closing sentence remain.

### Second update — revise attendance and add the event budget

The user runs `st-update -s 2 workshop.json`. Because the container now has two reports, source selection is required. Report 2 supplies the source, and Cross appends report 3 and prints its assigned index.

This is a new update for changed circumstances. To refine the accessibility update without adding another report instead, use `st-update -s 1 --iterate 2 workshop.json`; that reopens its prior update request and replaces report 2.

**Update prompt:**

```text
Attendance is now 18. Refreshments cost $3 per person. The total event budget
is $120, with no other costs in this exercise. Main Hall has offered a new
room-hire quote of $60, replacing its earlier $70 quote. Cedar stays at $40.
Show total costs and confirm whether the recommendation still works.
```

**Context used:** the saved report 2, its associated update prompt, and this new request. No replay of report 1 is needed for this appended update; report 2 already contains the access requirement and human edits.

The command saves report 3 and prints its update summary by default. The user could run `st-update -s 2 --update-details workshop.json` instead to request detailed review from that same update operation. Running another plain update afterward would create another report; it is not a command to redisplay the previous summary.

```text
Saved report 3 in workshop.json — based on report 2
- Changed attendance to 18 and Main Hall hire to $60.
- Added refreshments and totals: Cedar $94; Main Hall $114.
- Retained the access requirement; Main Hall meets the $120 budget.
Evidence: attendance, prices, and budget supplied in the update request.
Limitations: costs and access have not been independently checked.
```

**Report 3 — updated output:**

```markdown
# Workshop venue choice

## Options

| Room | Hire | Capacity | Access | Refreshments | Total |
|---|---:|---:|---|---:|---:|
| Cedar Room | $40 | 16 | Stairs only | $54 | $94 |
| Main Hall | $60 | 24 | Step-free | $54 | $114 |

Attendance is now 18. Refreshments cost 18 × $3 = $54. Main Hall’s new $60 quote replaces its earlier $70 quote. These totals include all costs specified for this exercise.

Cedar Room is below the $120 budget but cannot accommodate 18 people and lacks the step-free access two participants need. Main Hall meets both requirements and leaves $6 within the budget.

## Recommendation

Choose Main Hall at the revised quote. Its $114 total meets the budget, capacity, and access requirements. Confirm the booking against the new quote.

Keep the event welcoming and practical.
```

**What changed:** attendance, one quote, cost columns, and budget analysis. Accessibility is retained without asking the user to repeat it. Cedar’s theoretical total is shown for comparison, not as an eligible recommendation.

The user can now choose the appropriate action; these commands are alternatives, not a batch to run together:

```bash
st-ls workshop.json
st-edit --view-only --markdown -s 3 workshop.json
st-edit -s 3 --markdown workshop.json           # make manual changes
st-update -s 2 --iterate 3 workshop.json         # refine the request and replace report 3
st-post -s 3 --site MySite workshop.json        # publish the reviewed report
st-rm -s 3 workshop.json                       # discard the local output instead
```

If circumstances change again, `st-update -s 3 workshop.json` appends report 4 from source report 3, provided report 3 was retained. Cross assigns the new index. Removing a local report does not undo an earlier Discourse post.

**Lesson for st-ask:** “Use the saved report as it exists now, including human edits. Append for a new update; use `--iterate` to refine an existing output. The original prompt must not undo a table or wording the user added later.”

## Example 2: Refresh a report as new data arrives

**Question this answers:** How do I keep a report current without mixing old and new measurements?

**Scenario:** A team reviews a fictional task-processing pilot. Each new log is a complete cumulative snapshot as of its stated date. It replaces the earlier counts; it is not another batch to add to them.

**Standing brief, retained for all three outputs:** “Write a short internal pilot report with Status, Findings, and Next step headings. Use supplied logs only. Distinguish observed results from general conclusions.” This is explicit carried intent, not an automatically generated summary of old prompts.

The user runs `st-new pilot` to create `pilot.prompt`, including the standing brief above and the prompt below in that file.

### Initial prompt

```text
Using the standing brief, report the pilot position as of November 1, 2026.
The supplied log contains 10 tasks: 6 completed, 2 pending, and 2 failed.
These categories are mutually exclusive. Report completed tasks as a share
of all recorded tasks. Do not treat pending tasks as failures or claim that
this small pilot proves performance in general.
```

After saving the prompt, the user generates and inspects the initial report:

```bash
st-gen pilot.prompt
st-ls pilot.json
st-edit -s 1 --markdown pilot.json
```

### Report 1 — initial output

```markdown
# Task-processing pilot

## Status

As of November 1, 2026, the supplied pilot log contains 10 tasks.

## Findings

- Completed: 6 of 10 (60%).
- Pending: 2 of 10.
- Failed: 2 of 10.

The completion share is provisional because two tasks remain pending. This small pilot does not establish performance outside the recorded tasks.

## Next step

Resolve the pending tasks and collect a larger sample before deciding whether to expand the pilot.
```

The container now contains one report with no fact-checks. The user may keep this internal report local, or publish it explicitly with `st-post -s 1 --site MySite pilot.json` after review.

### First update — replace the counts with a larger snapshot

The user runs `st-update pilot.json`, or explicitly `st-update -s 1 pilot.json`, and enters the request below in the editor. The command appends report 2 and prints a summary. Use `st-update --update-details pilot.json` instead when detailed review is wanted for this operation.

**Update prompt:**

```text
Update the report as of November 8, 2026. The new cumulative log contains
20 tasks in total: 14 completed, 4 pending, and 2 failed. It includes the
original 10 tasks; do not add the snapshots together. Replace the current
counts and completion share. Keep the limitations clear.
```

**Context used:** report 1, its prompt and included standing brief, and the new supplied snapshot/request. The date comes from the supplied log; `st-update` is not fetching live results.

**Summary after saving report 2 (illustrative):**

```text
Saved report 2 in pilot.json — based on report 1
- Replaced the November 1 snapshot with November 8 totals.
- Changed completion to 14 of 20 (70%), pending to 4, and kept failed at 2.
- Kept the small-sample limitation and updated the next action.
Evidence: cumulative log supplied in the update request.
Limitations: no independent log validation or explanation of outcome changes.
```

**Report 2 — updated output:**

```markdown
# Task-processing pilot

## Status

As of November 8, 2026, the supplied cumulative pilot log contains 20 tasks. This snapshot includes the original 10 tasks and replaces the earlier counts.

## Findings

- Completed: 14 of 20 (70%).
- Pending: 4 of 20.
- Failed: 2 of 20.

The completion share remains provisional because four tasks are pending. The larger snapshot still does not establish performance outside the pilot or explain why outcomes differ.

## Next step

Resolve the four pending tasks and review the failure reasons before deciding whether to expand the pilot.
```

**What changed:** the reporting date, denominator, counts, and next action. The total is 20, not 30. The report retains its headings, bullet structure, and cautious interpretation.

After reviewing the summary, the user can inspect the report with `st-edit --view-only --markdown -s 2 pilot.json`, edit it with `st-edit -s 2 --markdown pilot.json`, or publish it with `st-post -s 2 --site MySite pilot.json`.

If the November 8 request needs correction, `st-update -s 1 --iterate 2 pilot.json` reopens that request and replaces report 2 after regeneration. If the output should be discarded, use `st-rm -s 2 pilot.json`. The following continuation assumes report 2 was retained.

### Second update — close the same cohort

The final log is new information, so the user runs `st-update -s 2 pilot.json`. The explicit source index is required because two reports exist. Cross appends report 3 from source report 2 and prints the new index.

**Update prompt:**

```text
Use the final November 15, 2026 log for the same 20-task cohort: 16 completed,
0 pending, and 4 failed. No new tasks were added. Update the report to show
that this cohort is complete, while retaining the small-sample limitation.
Recommend reviewing the four failures before any expansion decision.
```

**Context used:** the saved report 2, its associated update prompt, the retained standing brief, and the final log/request. Report 1 and its counts do not need to be sent again for this appended update.

**Summary after saving report 3 (illustrative):**

```text
Saved report 3 in pilot.json — based on report 2
- Replaced the counts with the final November 15 log for the same 20 tasks.
- Changed completion to 16 of 20 (80%), pending to 0, and failed to 4.
- Marked this cohort complete and retained the limit on general conclusions.
Evidence: final cohort log supplied in the update request.
Limitations: the log does not explain failures or establish wider performance.
```

**Report 3 — updated output:**

```markdown
# Task-processing pilot

## Status

As of November 15, 2026, the supplied final log covers the same 20-task cohort. No new tasks were added, and none remain pending.

## Findings

- Completed: 16 of 20 (80%).
- Pending: 0 of 20.
- Failed: 4 of 20.

The cohort’s completion share is now final. These results describe this small pilot; they do not establish performance in other workloads or explain the failures.

## Next step

Review the four failures before deciding whether to expand. Use that review to define what a further pilot would need to test.
```

**What changed:** the final counts, provisional status, and next action. “Final” refers to this cohort’s supplied results, not independent fact-checking or a final decision to deploy.

The user confirms the saved entries with `st-ls pilot.json` and views report 3 with `st-edit --view-only --markdown -s 3 pilot.json`. They can then publish it with `st-post -s 3 --site MySite pilot.json`, manually edit it with `st-edit -s 3 --markdown pilot.json`, refine its request with `st-update -s 2 --iterate 3 pilot.json`, or discard it with `st-rm -s 3 pilot.json`. These are alternatives. A later `st-update -s 3 pilot.json` appends another output from existing source report 3; Cross assigns and prints its index.

**Lesson for st-ask:** “Supply new evidence and explain whether it replaces earlier measurements or adds to them. Review the saved result, then decide whether to keep, edit, iterate, publish, or discard it. Changing a date does not fetch current evidence.”

## Example 3: Incorporate selected Discourse feedback

**Question this answers:** Can I use community feedback without letting every comment rewrite the proposal?

**Scenario:** A fictional makerspace publishes a shared-tool booking proposal and receives feedback. The user copies selected comments into update requests. Updating the local report does not fetch comments or publish automatically; the user runs `st-post` separately after review. It does not update the original post. Reposting the same title on the same site fails; a later publication needs a distinct title.

**Standing brief:** “Write for makerspace members. Keep the headings Proposal, Access, and Review, and a welcoming, direct tone. This pilot must not give priority in exchange for payment.”

The user runs `st-new booking` to create `booking.prompt`, including the standing brief above and the prompt below.

### Initial prompt

```text
Write a short proposal for a two-week shared-tool booking pilot using the
standing brief. Start with 60-minute slots, one future booking per member,
and an online booking form. During the pilot, record unused bookings and
member feedback so the rules can be reviewed afterward.
```

The user generates, lists, and inspects the report:

```bash
st-gen booking.prompt
st-ls booking.json
st-edit -s 1 --markdown booking.json
```

### Report 1 — initial output

```markdown
# Shared-tool booking pilot

## Proposal

Run a two-week pilot with 60-minute slots and one future booking per member. All members use the same booking rules; payment does not buy priority.

## Access

Members reserve a slot through the online booking form. Please cancel a booking you cannot use so another member can take it.

## Review

Record unused bookings and member feedback during the pilot. At the end of two weeks, review whether the slot length and booking process meet members’ needs.
```

Once satisfied, the user runs `st-post -s 1 --site MySite booking.json`. The local container contains one report with no fact-checks. Comments arrive on Discourse; the user selects the comments to include below.

### First update — accept two comments and exclude one

The user runs `st-update booking.json` to select report 1 and open the update editor. `st-update -s 1 booking.json` is equivalent here. The command appends report 2 and prints its update summary; the alternative `st-update --update-details booking.json` requests detailed review for that operation.

**Update prompt, including the selected fictional feedback:**

```text
Revise the proposal using these comments from the fictional pilot topic:
- Comment #12: “Some members cannot use the online form. Could the front desk book for them?”
- Comment #13: “Some projects need two hours. Could we allow a 120-minute slot?”
- Comment #14: “Let members pay for priority booking.”

Accept #12 and #13: allow front-desk bookings into the same calendar and
let members choose 60 or 120 minutes. Retain one future booking per member.
Do not incorporate #14; paid priority conflicts with the standing brief.
```

**Context used:** report 1, its prompt and included standing brief, and the user’s explicit selection above. The comments are suggestions, not verified evidence that a particular policy will succeed. Their labels preserve which feedback led to which change.

**Summary after saving report 2 (illustrative):**

```text
Saved report 2 in booking.json — based on report 1
- Added front-desk bookings into the same calendar, from comment #12.
- Added a 120-minute option alongside 60 minutes, from comment #13.
- Retained one future booking per member and excluded paid priority (#14).
Sources: selected comments and the user's acceptance/rejection instructions.
Limitations: these suggestions do not establish that the revised policy will work.
```

**Report 2 — updated output:**

```markdown
# Shared-tool booking pilot

## Proposal

Run a two-week pilot with a choice of 60- or 120-minute slots and one future booking per member. All members use the same booking rules; payment does not buy priority.

## Access

Members can reserve through the online form or ask the front desk to make the booking. Both routes use the same calendar and availability. Please cancel a booking you cannot use so another member can take it.

## Review

Record unused bookings and member feedback during the pilot. At the end of two weeks, review whether both slot lengths and both booking routes meet members’ needs.
```

**What changed:** slot length choices and access routes. One-booking limits, equal access, headings, and tone remain. The paid-priority suggestion does not become policy merely because it appeared in the input.

The user inspects report 2 with `st-edit --view-only --markdown -s 2 booking.json`. They may edit it with `st-edit -s 2 --markdown booking.json` or refine the same update with `st-update -s 1 --iterate 2 booking.json`. When satisfied and after choosing a distinct posting title, `st-post -s 2 --site MySite booking.json` publishes the selected output as a separate action. Alternatively, `st-rm -s 2 booking.json` discards the local output; it does not remove a published post.

### Second update — respond to pilot observations

Assuming report 2 was retained, the user runs `st-update -s 2 booking.json`. Report 2 is the explicitly selected source; Cross appends report 3 and prints its index.

**Update prompt:**

```text
The organizer’s supplied first-week log records four bookings where nobody
arrived. It does not record reasons or the total number of bookings, so do
not calculate a no-show rate or blame a booking route.

New fictional comment #20 suggests a reminder and releasing unused slots.
For the remainder of the pilot, add an opt-in reminder by the member’s chosen
available contact method. If the member is 15 minutes late and has not
contacted the front desk, release the remaining booked time for someone else.
Keep both booking routes and slot lengths, and do not add penalties or fees.
```

**Context used:** the saved report 2, its immediate update prompt as previous intent, the retained standing brief, and this request/log. The instruction to reject paid priority remains in effect. No earlier full report or automatic topic fetch is needed for this appended update.

**Summary after saving report 3 (illustrative):**

```text
Saved report 3 in booking.json — based on report 2
- Added an opt-in reminder and a 15-minute release rule, following comment #20.
- Added the observation of four unattended bookings without inventing a rate.
- Kept both booking routes, both slot lengths, and the prohibition on fees.
Sources: organizer's supplied log, selected comment, and user instructions.
Limitations: the total booking count and reasons for absence are unknown.
```

**Report 3 — updated output:**

```markdown
# Shared-tool booking pilot

## Proposal

Continue the two-week pilot with a choice of 60- or 120-minute slots and one future booking per member. All members use the same booking rules; payment does not buy priority. No penalties or fees are introduced.

## Access

Members can reserve through the online form or ask the front desk to make the booking. Both routes use the same calendar and availability. Please cancel a booking you cannot use so another member can take it.

For the remainder of the pilot, offer an opt-in reminder using the member’s chosen available contact method. If a member is 15 minutes late and has not contacted the front desk, release the remaining booked time for someone else.

## Review

The organizer’s first-week log records four unattended bookings. Without the total booking count or reasons, it does not establish a no-show rate or show that either booking route caused the problem.

Continue recording unused bookings and member feedback. At the end of two weeks, review both slot lengths, both booking routes, and members’ experience of the reminder and release rules.
```

**What changed:** the reminder/release proposal and the review evidence. Earlier accepted improvements survive. Generating the report sends no reminders, edits no calendar, and publishes nothing automatically.

The user runs `st-ls booking.json` and `st-edit --view-only --markdown -s 3 booking.json` to find and inspect the result. They can publish with `st-post -s 3 --site MySite booking.json`, edit with `st-edit -s 3 --markdown booking.json`, regenerate in place with `st-update -s 2 --iterate 3 booking.json`, or discard locally with `st-rm -s 3 booking.json`. A further `st-update -s 3 booking.json` appends another output if source report 3 was retained; Cross assigns the new index. These are alternative next actions, not an automatic chain.

**Lesson for st-ask:** “Choose which feedback becomes instructions. Preserve the source references, but do not treat every comment as a fact or an accepted change. Generating a revision does not publish it.”
