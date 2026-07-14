# Terminal Setup — Rendered Output & Clickable Links

Cross renders its AI answers as **styled, easy-to-read output** — headings, bold, bullet lists, syntax-highlighted code, and **clickable links** — in any terminal that supports it. Tools like [st-ask](st-ask) and [st-verdict](st-verdict) use this automatically. Everything still works in a plain terminal; you just get bare text and non-clickable URLs.

This is optional polish, **not** a requirement.

---

## Recommended terminal (macOS): iTerm2

For the nicest experience on macOS — truecolor and clickable links — we recommend [iTerm2](https://iterm2.com):

```bash
brew install --cask iterm2
```

Then open **iTerm** and run any Cross command as usual. Links in answers (e.g. wiki pages in a `See also:` block) become clickable.

> The built-in macOS **Terminal.app** shows Cross output fine but does not make links clickable. iTerm2 does.

## Terminals that already work well

Clickable links and colour work out of the box in:

- **iTerm2** (macOS)
- **VS Code** integrated terminal
- **WezTerm**, **Kitty**, **Alacritty**
- **Windows Terminal** (Windows / WSL2 — see [Windows / WSL2](Windows-WSL2))
- **GNOME Terminal**, **Konsole** (Linux)

No configuration needed — Cross detects the terminal and renders accordingly.

---

## Turning rendering off (raw markdown)

Sometimes you want the raw markdown — to copy-paste, pipe, or save to a file. Cross keeps that easy:

| How | Result |
|-----|--------|
| `st-ask --no-render "…"` / `st-verdict --no-render …` | Raw markdown for that run |
| `st-ask "…" \| pbcopy` (any pipe/redirect) | Raw markdown automatically (rendering only applies to a live terminal) |
| `:raw` / `:render` in the `st-ask` REPL | Toggle rendering mid-session |
| `NO_COLOR=1` | Disables rendering (the community-standard env var) |
| `CROSS_MARKDOWN=off` in `~/.crossenv` | Global kill-switch — never render, everywhere |

So piping and redirecting are **already** raw — you only need `--no-render` when you want raw output in an interactive terminal.

---

## See also

- [st-ask](st-ask) — local help assistant (renders answers)
- [st-verdict](st-verdict) — verdict chart + AI analysis (renders the written analysis)
- [Onboarding](Onboarding) — first-time setup
- [Windows / WSL2](Windows-WSL2) — Windows Terminal setup

