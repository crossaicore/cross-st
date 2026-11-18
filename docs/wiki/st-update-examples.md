# st-update worked examples

These fictional examples illustrate intended edits and expected report content.
The outputs are teaching examples, not live AI results or guarantees. The command
is available in the next release. See [st-update](st-update) for review, approval,
revision history, and implementation limits.

## How to read the examples

Each example starts with an **alpha prompt and the complete saved alpha report**, then shows **two update prompts and complete revised reports**. Reports are deliberately short so the changes are easy to follow; real reports may be longer.

Each example uses its own container with one initial report. The sequence is **v1 → v2 → v3**. On the second update, v2 is the alpha: “alpha” means the report selected for this update, not permanently the original v1. The version footer identifies the saved report version and its immediate parent:

```text
Report v1
Report v2 · Based on v1
Report v3 · Based on v2
```

Cross supplies this line from metadata after generation. The model does not choose the version number. The examples show the version line; the normal Cross attribution would remain alongside it in actual output. A version number says nothing about factual accuracy or publication status.

All three workflows leave fact-checking **off**. `--check` would explicitly request checks of the new report, while `--with-facts` would include existing alpha findings as generation context. Neither is needed here. Reports use the supplied fictional material, and their footers do not claim verification.

These illustrative commands use existing example containers. Each plain `st-update FILE.json` invocation opens the editor for the update prompt shown below. After editing, the AI analyzes the supplied material and displays a proposed update summary. Each revised report below assumes the user approved that plan before generation. `--update-details` shows the detailed view; `--update-summary` explicitly selects the concise default. Neither view runs fact-checks or implies web browsing. The initial alpha prompt belongs to the original creation process; it is not a command to regenerate v1 during an update.

## Example 1: Fill gaps in a human-edited report

**Question this answers:** Can I add missing considerations without losing my own edits or the report’s formatting?

**Scenario:** A volunteer organizer compares two rooms for a workshop. The initial prompt asked for paragraphs, but the organizer replaced that section with a table and added the sentence “Keep the event welcoming and practical.” The saved, edited Markdown is the alpha. It becomes v1 when revision tracking is first adopted; its earlier unsaved editing steps are not reconstructed.

### Alpha prompt

```text
Write a short report helping a volunteer organizer choose a room for a
10-person workshop. Use the headings Options and Recommendation, with
short paragraphs. Keep the tone practical and welcoming.

Supplied quotes:
- Cedar Room: $40 room hire, capacity 16.
- Main Hall: $70 room hire, capacity 24.
Choose a room on the information available. Identify missing information.
```

### Alpha report — v1, including the human edits

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

---
*Report v1*
```

### First update — add the missing accessibility information

Command: `st-update workshop.json`.

**Update prompt:**

```text
Two participants need step-free access. The venue coordinator has confirmed
that Cedar Room is reached only by stairs and Main Hall has step-free access.
Add this information and revise the recommendation. Attendance is still 10.
```

**Context used:** the saved v1 Markdown, its alpha prompt, and this update request. No checks or earlier raw AI output are needed. The old request for paragraphs must not remove the human’s table.

**Review before applying (illustrative):**

```text
Proposed update summary — based on v1
- Add access information for both rooms to the Options table.
- Recommend Main Hall because two participants need step-free access.
- Retain attendance, prices, headings, and the human closing sentence.
Evidence: venue coordinator information supplied in your update request.
Limitations: no independent access check; other event costs remain unknown.
Approve / Details / Revise request / Cancel:
```

The detailed view would list items such as `U1: Options table — add Access column: Cedar Room = stairs only; Main Hall = step-free`, with the coordinator statement as its source, and `U2: Recommendation — choose Main Hall`, with the access requirement as its reason. These are proposed changes, not a revised report. The user can revise or cancel before generation. The following v2 assumes approval.

**Updated report — v2:**

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

---
*Report v2 · Based on v1*
```

**What changed:** an Access column and the recommendation. The title, two headings, table presentation, practical tone, and human closing sentence remain.

### Second update — revise attendance and add the event budget

Command: `st-update workshop.json` again, now using v2 as alpha.

**Update prompt:**

```text
Attendance is now 18. Refreshments cost $3 per person. The total event budget
is $120, with no other costs in this exercise. Main Hall has offered a new
room-hire quote of $60, replacing its earlier $70 quote. Cedar stays at $40.
Show total costs and confirm whether the recommendation still works.
```

**Context used:** v2, the first update prompt as its immediate intent, and this new request. No replay of v1 is needed; v2 already contains the access requirement and human edits.

**Updated report — v3:**

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

---
*Report v3 · Based on v2*
```

**What changed:** attendance, one quote, cost columns, and budget analysis. Accessibility is retained without asking the user to repeat it. Cedar’s theoretical total is shown for comparison, not as an eligible recommendation.

**Lesson for st-ask:** “Use the saved report as it exists now, including human edits. The original prompt helps explain intent but must not undo a table or wording the user added later.”

## Example 2: Refresh a report as new data arrives

**Question this answers:** How do I keep a report current without mixing old and new measurements?

**Scenario:** A team reviews a fictional task-processing pilot. Each new log is a complete cumulative snapshot as of its stated date. It replaces the earlier counts; it is not another batch to add to them.

**Standing brief, retained for all three versions:** “Write a short internal pilot report with Status, Findings, and Next step headings. Use supplied logs only. Distinguish observed results from general conclusions.” This is explicit carried intent, not an automatically generated summary of old prompts.

### Alpha prompt

```text
Using the standing brief, report the pilot position as of November 1, 2026.
The supplied log contains 10 tasks: 6 completed, 2 pending, and 2 failed.
These categories are mutually exclusive. Report completed tasks as a share
of all recorded tasks. Do not treat pending tasks as failures or claim that
this small pilot proves performance in general.
```

### Alpha report — v1

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

---
*Report v1*
```

### First update — replace the counts with a larger snapshot

Command: `st-update pilot.json`.

**Update prompt:**

```text
Update the report as of November 8, 2026. The new cumulative log contains
20 tasks in total: 14 completed, 4 pending, and 2 failed. It includes the
original 10 tasks; do not add the snapshots together. Replace the current
counts and completion share. Keep the limitations clear.
```

**Context used:** v1, its prompt, the standing brief, and the new supplied snapshot/request. The date comes from the supplied log; `st-update` is not fetching live results.

**Updated report — v2:**

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

---
*Report v2 · Based on v1*
```

**What changed:** the reporting date, denominator, counts, and next action. The total is 20, not 30. The report retains its headings, bullet structure, and cautious interpretation.

### Second update — close the same cohort

Command: `st-update pilot.json` again, now using v2 as alpha.

**Update prompt:**

```text
Use the final November 15, 2026 log for the same 20-task cohort: 16 completed,
0 pending, and 4 failed. No new tasks were added. Update the report to show
that this cohort is complete, while retaining the small-sample limitation.
Recommend reviewing the four failures before any expansion decision.
```

**Context used:** v2, its associated update prompt, the standing brief, and the final log/request. v1 and its counts do not need to be sent again.

**Updated report — v3:**

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

---
*Report v3 · Based on v2*
```

**What changed:** the final counts, provisional status, and next action. “Final” refers to this cohort’s supplied results, not independent fact-checking or a final decision to deploy.

**Lesson for st-ask:** “Updating a report’s date does not fetch current evidence. Supply the new material and explain whether it replaces earlier measurements or adds to them. Version numbers and as-of dates serve different purposes.”

## Example 3: Incorporate selected Discourse feedback

**Question this answers:** Can I use community feedback without letting every comment rewrite the proposal?

**Scenario:** A fictional makerspace publishes a shared-tool booking proposal and receives feedback. The user copies selected comments into update requests. This is the proposed MVP workflow; it does not require automatic Discourse retrieval or publish an update back to the topic.

**Standing brief:** “Write for makerspace members. Keep the headings Proposal, Access, and Review, and a welcoming, direct tone. This pilot must not give priority in exchange for payment.”

### Alpha prompt

```text
Write a short proposal for a two-week shared-tool booking pilot using the
standing brief. Start with 60-minute slots, one future booking per member,
and an online booking form. During the pilot, record unused bookings and
member feedback so the rules can be reviewed afterward.
```

### Alpha report — v1

```markdown
# Shared-tool booking pilot

## Proposal

Run a two-week pilot with 60-minute slots and one future booking per member. All members use the same booking rules; payment does not buy priority.

## Access

Members reserve a slot through the online booking form. Please cancel a booking you cannot use so another member can take it.

## Review

Record unused bookings and member feedback during the pilot. At the end of two weeks, review whether the slot length and booking process meet members’ needs.

---
*Report v1*
```

### First update — accept two comments and exclude one

Command: `st-update booking.json`.

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

**Context used:** v1, its prompt, the standing brief, and the user’s explicit selection above. The comments are suggestions, not verified evidence that a particular policy will succeed. Their labels preserve which feedback led to which change.

**Updated report — v2:**

```markdown
# Shared-tool booking pilot

## Proposal

Run a two-week pilot with a choice of 60- or 120-minute slots and one future booking per member. All members use the same booking rules; payment does not buy priority.

## Access

Members can reserve through the online form or ask the front desk to make the booking. Both routes use the same calendar and availability. Please cancel a booking you cannot use so another member can take it.

## Review

Record unused bookings and member feedback during the pilot. At the end of two weeks, review whether both slot lengths and both booking routes meet members’ needs.

---
*Report v2 · Based on v1*
```

**What changed:** slot length choices and access routes. One-booking limits, equal access, headings, and tone remain. The paid-priority suggestion does not become policy merely because it appeared in the input.

### Second update — respond to pilot observations

Command: `st-update booking.json` again, now using v2 as alpha.

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

**Context used:** v2, its immediate update prompt as previous intent, the standing brief, and this request/log. The previous instruction to reject paid priority remains background, not an invitation to reconsider it. No earlier full report or automatic topic fetch is needed.

**Updated report — v3:**

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

---
*Report v3 · Based on v2*
```

**What changed:** the reminder/release proposal and the review evidence. Earlier accepted improvements survive. The example drafts a policy; it sends no reminders, edits no calendar, and posts nothing to Discourse.

**Lesson for st-ask:** “Choose which feedback becomes instructions. Preserve the source references, but do not treat every comment as a fact or an accepted change. Generating a revision does not publish it.”

