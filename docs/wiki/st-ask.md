# st-ask — Local FAQ Help (Pseudo-AI)

`st-ask` provides instant, local help for common Cross questions — no API key required. It matches your question to a built-in FAQ using semantic and fuzzy search. For full LLM-powered answers, add an API key with `st-admin --setup`.

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

## Features
- No API key required
- Local, privacy-preserving
- Suggests Discourse/GitHub links if no match
- Redacts secrets/paths in error breadcrumbs

## Escape Hatches
- [GitHub Discussions](https://github.com/crossaicore/cross-st/discussions)
- [Cross Community](https://crossai.dev/community)

---

(local lookup — for full answers add an AI key with 'st-admin --setup')

