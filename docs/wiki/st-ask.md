# st-ask — Local FAQ Help (Pseudo-AI)

`st-ask` provides instant, local help for common Cross questions — no API key required. It matches your question to a built-in FAQ using word-based TF-IDF and fuzzy matching. For full LLM-powered answers, add an API key with `st-admin --setup`.

## Usage

- `st-ask "How do I install cross-st?"` — one-shot answer
- `st-ask` — interactive REPL

## Rendered output

Answers are shown as **rendered markdown** — styled headings, lists, code, and clickable links — when you run `st-ask` in a capable terminal. Piped or redirected output (e.g. `st-ask "…" | pbcopy`) stays **raw markdown** so it's easy to copy and reuse.

| Flag / command | Effect |
|----------------|--------|
| `--no-render` | Print raw markdown instead of styled output |
| `:raw` / `:render` (in the REPL) | Toggle rendering mid-session |

For clickable links, see [Terminal Setup](Terminal-Setup) (macOS: `brew install --cask iterm2`). Set `CROSS_MARKDOWN=off` in `~/.crossenv` to disable rendering everywhere.

## Feedback & telemetry (opt-in)

If you have opted in to anonymous usage telemetry (`st-admin --ask-telemetry on`), `st-ask` shows a one-keystroke **thumb-up/down** prompt after each answer:

```
  Was this helpful? [y/n, Enter to skip]:
```

It's always skippable (press Enter) and never blocks. The result feeds the anonymous, scrubbed telemetry event that helps prioritise FAQ improvements — the client applies pattern-based redaction before sending question text. Redaction is best effort; avoid including secrets or personal information in questions. Telemetry stays **off** until you opt in.

| Flag | Effect |
|------|--------|
| `--no-feedback` | Skip the post-answer thumb-up/down prompt |

The prompt only appears when telemetry is enabled **and** you're in an interactive terminal; it's automatically silent when piped or scripted.

## Features
- No API key required
- Local lookup with `--pseudo`; optional telemetry can still send the scrubbed question
- Suggests Discourse/GitHub links if no match
- Redacts secrets/paths in error breadcrumbs

## Escape Hatches
- [Cross Community (Discourse)](https://crossai.dev)
- [GitHub Issues](https://github.com/crossaicore/cross-st/issues)

---

(local lookup — for full answers add an AI key with 'st-admin --setup')


## Additional current options

- `--agent`: Agent name to use for LLM tier
- `--pseudo`: Force Pseudo-AI tier even if API key present
- `--explain-last-error`: Explain the last error using the LLM tier

## Knowledge sources and limits

Local mode reads the bundled `cross_st/data/support_faq.md` (YAML despite the
`.md` extension). It matches questions and aliases, returns a canned answer
above confidence 0.6, suggests up to three questions above 0.3, and otherwise
reports no match. It does not search the entire wiki. Error signatures are
reserved metadata and are not yet used for matching.

AI mode passes the bundled `cross_st/data/support_content.md` as reference
material on each call. This includes FAQ answers, local wiki pages, current
CLI argument declarations, and the changelog. The model is instructed to use
only this material and admit missing coverage; this is not a guarantee of
correctness. It does not automatically synchronize the online wiki. Each REPL
question is independent: previous questions and answers are not sent as history.
Agent selection is `--agent`, then `ASK_AGENT`, then the configured default.
Currently automatic AI-mode detection checks only four API-key environment
variables (OpenAI, Anthropic, Gemini, xAI); keyless local agents and other
providers are not detected by this gate.

With telemetry enabled, events go to `https://crossai.dev/api/ask-telemetry`.
They contain scrubbed question text, mode, answer-returned status, agent,
optional helpfulness feedback, package version, and a UTC timestamp. Answers
are not included. Sending is best effort: the background daemon thread may
exit before a one-shot command finishes delivery. A returned AI answer does
not mean it was verified or supported by the corpus.

Maintainers expand the FAQ and wiki, run `python script/build_ask_corpus.py`,
then validate with `python script/build_ask_corpus.py --check-current`.
Package releases distribute the new knowledge. Telemetry is a source of
questions to investigate, not a source of factual answers to import directly.
