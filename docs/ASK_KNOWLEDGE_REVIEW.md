# st-ask knowledge review — 2026-09-21

This review traces the local cross-st and cross-internal source checkouts.
Server paths below are configured defaults, not a claim that production was
queried or that every client event was delivered. No production telemetry or
paid AI requests were used in this audit.

## Knowledge acquisition and answering

The editable sources are `cross_st/data/support_faq.md` (YAML),
`docs/wiki/*.md`, and `CHANGELOG.md`. `script/build_ask_corpus.py` combines them
into the shipped `cross_st/data/support_content.md`. This audit also adds a
current argument reference extracted from every entry point's source. The
builder never executes CLI commands or calls AI. It does not fetch the online
wiki, community discussions, GitHub issues, telemetry, or arbitrary READMEs.
Changes reach pipx users through a package release and upgrade.

Before this review, local mode used five hardcoded answers despite a curated
15-entry FAQ file. It now loads that FAQ and matches each question and alias. Two entries preserve
the former help and uninstall answers, bringing the curated total to 17.
The matcher combines TF-IDF cosine similarity (70%) and fuzzy token matching
(30%), keeping the strongest phrasing for each unique FAQ entry. Above 0.6 it
returns the stored answer; above 0.3 it suggests questions; otherwise it admits
no match. This is lexical retrieval, not an embedding model. Local mode still
does not search the entire wiki or provide comprehensive help for every command.
The FAQ's error-signature metadata is not consumed yet.

AI mode sends the entire bundled corpus in the system prompt and the current
question as the user message. It is instructed to stay within the reference,
admit missing coverage, and link commands to their wiki pages. It has no
retrieval step, source-verification pass, or persistent conversational memory.
A REPL turn does not include prior turns. `--explain-last-error` additionally
reads and scrubs the last cached error breadcrumb.

Agent selection is `--agent` → `ASK_AGENT` → `get_default_ai()`. Mode detection
is a separate, incomplete gate: only OpenAI, Anthropic, Gemini and xAI API-key
environment variables are checked. Keyless Ollama and other providers can be
wrongly routed to local mode. A key for one provider also does not establish
that the selected agent is usable. This remains a follow-up defect.

The reference is about 294 KB after rebuilding. Sending all history and all
wiki pages on every question can add cost, exceed smaller models' context
budgets, and present contradictory historical instructions. Provider caching
can reduce repeated work but does not establish factual accuracy. Current
arguments now take precedence in the prompt over historical changelog examples.

## Where shared analytics go

Client: `cross_st/_ask_telemetry.py`, enabled only by
`CROSS_ASK_TELEMETRY=on`; user interface: `st-admin --ask-telemetry on|off`.
The default POST destination is `https://crossai.dev/api/ask-telemetry`.
`CROSS_ASK_TELEMETRY_URL` can override it.

Receiver: `cross-internal/discourse/server_app/app.py`, route
`POST /api/ask-telemetry`. It appends to SQLite table `ask_telemetry` in
`DB_PATH`, whose default is `/opt/crossai-provision/data/provision.db`.
Columns include question, mode, matched, agent, helpful, package version,
client timestamp, server receipt timestamp and row ID. Questions are truncated
to 500 characters. Answer text, FAQ ID, match confidence, exact model and corpus
hash are not captured.

Review UI: `https://crossai.dev/crossai-admin/ask`, implemented in
`cross-internal/discourse/server_app/admin/routes.py`. Its default window is
seven days, adjustable with `?days=30`. It shows aggregate helpful/unhelpful
counts, weekly volume, and the top 100 no-match questions grouped by exact
question and tier. It does not currently provide a per-question negative-
feedback queue, synonym clustering, or a resolved/imported status.

Important limitations in the measurements:

- The client submits scrubbed questions for answered and unanswered queries,
  not just no-matches. Earlier design notes describe a narrower policy.
- The scrubber replaces the current home directory and a few token patterns.
  It does not guarantee removal of emails, names, arbitrary paths or every
  provider's secret format. Privacy claims must reflect this limitation.
- Delivery uses a daemon thread with no persistence, acknowledgement handling,
  retry queue or exit flush. One-shot commands can exit before delivery.
- Previously even failed AI calls were recorded as `matched=true`. This review
  fixes that. Successful AI output still means only that text was returned,
  not that the answer was correct or that the corpus covered the question.
- Corpus version is not separately recorded. A package version alone cannot
  distinguish locally rebuilt knowledge from the published reference.

## Turning analytics into reviewed knowledge

There is no existing automatic importer. Keep telemetry as a source of demand,
not as trusted factual content. A practical maintenance cycle is:

1. Review the no-match queue and negative feedback weekly, grouped by package
   version and mode. Add a query-level negative-feedback view on the server.
2. Scrub and normalize questions; combine variants into a topic. Keep private
   raw records out of public repository commits.
3. Reproduce the user's task with the current CLI, source and fixture data.
   Decide whether the issue is missing documentation, a matcher miss, a product
   defect, or a question outside Cross's scope.
4. Write a verified FAQ answer or update the appropriate wiki page. Add user
   phrasings as aliases. Never copy a user's premise into an answer unchecked.
5. Add a regression query with expected FAQ ID, required facts and forbidden
   flags. Include ambiguous, out-of-scope and outdated-version questions.
6. Rebuild, review the generated diff, run the checks below, and publish a new
   package release. Record the issue/FAQ ID and release in a private triage log.
7. Compare answer rate and helpfulness after release, accounting for delivery
   loss, opt-in sampling and changed question mix.

A future event schema should include corpus hash/version, matched FAQ ID,
confidence, outcome (`answered`, `suggested`, `no_match`, `error`), and model
identity. Introduce it with a coordinated server migration and updated consent.
These additions are recommendations, not implemented in this change.

## Command-by-command verification

See `docs/ASK_COMMAND_AUDIT.md` for all 30 entry points (29 `st-*` commands and
`st`). The audit derives the inventory from `pyproject.toml`, rather than a
hardcoded list that could miss new commands. It reads literal argparse
argument names and help descriptions; st-man's manual parser is represented
explicitly. This is a syntactic coverage check, not proof of behavior.

Every command already had a wiki page. Missing option descriptions were added
for st-admin, st-ask, st-fix, st-ls, st-new, st-prep, st-print, st-read,
st-speak and st-stones. All public declared long options are now mentioned in their
own pages. Every public current argument declaration is also included in the rebuilt
AI corpus, with its own command heading and source path.

The prose review corrected fixed-provider defaults in st-bang, st-fact,
st-heatmap, st-merge, st-stones and st-verdict; obsolete `st-gen --prep`
instructions; and the old `cross-ai[tts]` package name. The wiki generator was
updated for the latter two so regeneration does not reintroduce them. The
upgrade FAQ now explains the pipx detection bug in the published 2026.9.0.

Extra option mentions in the audit are a review queue, not automatic failures:
for example, st-fact documents flags that moved to st-verdict, while st-new
refers to st-admin's template initialization. Historical examples need context.

## Validation and what it proves

Run from the repository with its dependencies installed:

```bash
python script/build_ask_corpus.py
python script/build_ask_corpus.py --check-current
python script/audit_ask_commands.py
pytest tests/test_ask_knowledge.py tests/test_ask_match.py tests/test_ask_llm.py tests/test_ask_render.py tests/test_ask_telemetry.py
```

The new tests load the real FAQ, check every canonical question and alias,
reject an unrelated question, ensure suggestions are distinct, exercise FAQ
links and failed-call analytics, and check corpus freshness and command
coverage. Existing tests exercise rendering, feedback and mocked AI calls.
`--check` retains its old schema-only meaning; use `--check-current` for a
release freshness gate. Freshness is now part of the normal pytest suite.

These checks do not prove that prose is true, an alias generalizes to all user
phrasing, a provider follows its instructions, or a command's actual effects
match its help text. Before calling the entire knowledge base accurate, add
and review at least one task scenario per command plus failure scenarios for
configuration, network, optional dependencies and publishing. Validate those
against safe fixtures/mocks; use explicit opt-in AI evaluations separately.
Track source lines, required answer facts and forbidden claims for each case.
Do not use an AI judge as the sole authority for its own answers.

## Follow-up priorities

1. Fix mode selection for the chosen agent, including keyless local providers.
2. Improve telemetry redaction and delivery; distinguish unsupported answers
   from successful transport; add corpus identity and a resolved triage queue.
3. Expand the 17 local FAQs to cover common tasks across all commands using
   reviewed questions and expected facts, not mechanically copied prose.
4. Introduce retrieval over current documentation with section provenance and
   bounded context; keep historical release notes separate from current usage.
5. Build the reviewed per-command behavioral/AI evaluation set described above.

The current work closes demonstrable source-wiring and coverage defects. It
is not a claim that all command behavior or generated AI answers are certified.

## CLI help smoke audit

All 30 source entry points were also invoked with `--help` under a temporary
home, telemetry disabled, a noninteractive subprocess and no AI calls. 25
returned successfully. Five could not expose help in that clean environment:
`st`, `st-analyze`, and `st-post` require Discourse configuration during startup;
`st-speak` and `st-voice` require optional TTS dependencies before parsing help.
These are existing startup limitations, not corpus-generation failures.
`st` help succeeds with the existing configured home. Internal `st-fix
--weights` is intentionally hidden by argparse and excluded from the public
reference. The smoke audit does not exercise generation, publishing, printing,
or other command effects.

Validation result: all 81 focused tests passed in the pre-push run; corpus
freshness check passed. No live AI
quality evaluation was run. These changes require a future package release to reach pipx users.
