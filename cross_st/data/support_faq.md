# cross-st support FAQ
#
# This file is the single source of truth for `st-ask` Pseudo-AI mode (no API
# key configured). It is read at runtime by `cross_st/_ask_match.py` and
# composed into `support_content.md` for the Full LLM tier by
# `script/build_ask_corpus.py`.
#
# Schema per entry:
#   id:                str — slug (kebab-case), unique, stable
#   question:          str — canonical phrasing used in the menu
#   aliases:           list[str] — alternate phrasings the matcher should hit
#   error_signatures:  list[str] — substrings tested first when input looks
#                                  like a traceback (--explain-last-error)
#   answer:            str — verbatim user-voice answer; markdown allowed
#   see_also:          list[str] — wiki / docs links surfaced after answer
#
# Editing rules:
#   - User-voice. Imagine a brand-new user with no jargon context.
#   - Prefer wiki links over inline duplication (the wiki is canonical).
#   - One canonical answer per concept; add aliases liberally.
#   - Tested via tests/test_ask_match.py — keep entries matching their
#     fixture queries at confidence ≥ 0.5 after edits.
---
- id: what-is-cross-st
  question: "What is cross-st?"
  aliases:
    - "what does cross-st do"
    - "what is this tool"
    - "what does this app do"
    - "explain cross-st"
  error_signatures: []
  answer: |
    cross-st generates AI fact-checked **research reports**. You give it a
    prompt, it asks several AI providers (xAI, Anthropic, OpenAI, Gemini,
    DeepSeek), then cross-checks each report against the others to flag
    claims that disagree. The result is a single report you can publish
    with confidence — including a verdict on what is true, false, or missing.

    Tagline: *AI reports. Cross-examined.*

    The 30-ish `st-*` commands cover the whole pipeline:
    GATHER (`st-fetch`, `st-gen`) → VERIFY (`st-fact`, `st-cross`) →
    INTERPRET (`st-verdict`, `st-analyze`) → PUBLISH (`st-post`, `st-print`).
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Home
    - https://github.com/crossaicore/cross-st/wiki/Three-Stages
    - https://crossai.dev

- id: install-pipx
  question: "How do I install cross-st?"
  aliases:
    - "install cross-st"
    - "pipx install cross-st"
    - "first time install"
    - "how do i set this up"
    - "getting started"
  error_signatures: []
  answer: |
    Recommended install (macOS / Linux):

    ```bash
    pipx install cross-st
    ```

    `pipx` keeps cross-st in its own isolated environment so it never fights
    with your system Python. After the install finishes, run:

    ```bash
    st-admin --setup
    ```

    …to configure your first AI key. Windows users: see the WSL2 guide.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Install
    - https://github.com/crossaicore/cross-st/wiki/Windows-WSL2

- id: install-windows
  question: "How do I install cross-st on Windows?"
  aliases:
    - "install windows"
    - "windows install"
    - "wsl install"
    - "wsl2"
  error_signatures: []
  answer: |
    Cross-st runs under **WSL2** (Windows Subsystem for Linux 2) on Windows.
    The native Windows Python install is not supported — pipx, dotenv, and
    the audio stack all assume a POSIX environment.

    Quick path:

    1. Open PowerShell as Administrator and run `wsl --install`.
    2. Reboot, open the new Ubuntu terminal.
    3. Inside Ubuntu: `pipx install cross-st`.

    Full step-by-step is in the WSL2 wiki page.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Windows-WSL2

- id: setup-wizard
  question: "How do I run the setup wizard?"
  aliases:
    - "first run setup"
    - "st-admin setup"
    - "configure cross-st"
    - "initial config"
  error_signatures: []
  answer: |
    After `pipx install cross-st`, run:

    ```bash
    st-admin --setup
    ```

    The wizard walks you through:

    1. Adding at least one AI provider key (xAI, Anthropic, OpenAI, Gemini,
       or DeepSeek).
    2. Picking a default agent (model alias).
    3. Optional: joining the crossai.dev community via invite link.
    4. Optional: configuring a self-hosted Discourse forum.

    All choices are written to `~/.crossenv`. Re-run anytime to add keys
    or change defaults.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/st-admin
    - https://github.com/crossaicore/cross-st/wiki/Agents

- id: get-anthropic-key
  question: "How do I get an Anthropic API key?"
  aliases:
    - "anthropic key"
    - "claude api key"
    - "get claude key"
    - "sign up anthropic"
  error_signatures: []
  answer: |
    1. Sign up at <https://console.anthropic.com>.
    2. Add a payment method (Anthropic does not offer a free tier).
    3. Settings → API Keys → **Create Key**.
    4. Copy the key (starts with `sk-ant-…`) and paste it when `st-admin
       --setup` prompts for `ANTHROPIC_API_KEY`.

    The key is stored in `~/.crossenv`. Models cross-st knows about include
    `claude-sonnet-4-5` and `claude-opus-4-5`; pick one in the agent wizard.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Agents
    - https://docs.anthropic.com/en/api/getting-started

- id: get-openai-key
  question: "How do I get an OpenAI API key?"
  aliases:
    - "openai key"
    - "gpt api key"
    - "chatgpt key"
    - "sign up openai"
  error_signatures: []
  answer: |
    1. Sign up at <https://platform.openai.com>.
    2. Settings → Billing → add a payment method.
    3. API Keys → **Create new secret key** (project-scoped is fine).
    4. Copy the key (starts with `sk-…`) and paste it when `st-admin --setup`
       prompts for `OPENAI_API_KEY`.

    Note: a ChatGPT subscription does **not** include API access. The two
    bills are separate.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Agents
    - https://platform.openai.com/docs/quickstart

- id: get-xai-key
  question: "How do I get an xAI API key?"
  aliases:
    - "xai key"
    - "grok api key"
    - "sign up xai"
  error_signatures: []
  answer: |
    1. Sign up at <https://console.x.ai>.
    2. Add a payment method.
    3. API Keys → **Create**.
    4. Copy the key (starts with `xai-…`) and paste it when `st-admin --setup`
       prompts for `XAI_API_KEY`.

    Models cross-st knows about include `grok-4` and `grok-3-latest`.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Agents
    - https://docs.x.ai/

- id: get-gemini-key
  question: "How do I get a Gemini API key?"
  aliases:
    - "gemini key"
    - "google ai key"
    - "google api key"
    - "sign up gemini"
  error_signatures: []
  answer: |
    1. Visit <https://aistudio.google.com/apikey>.
    2. Sign in with a Google account and click **Create API key**.
    3. Copy the key and paste it when `st-admin --setup` prompts for
       `GEMINI_API_KEY` (also accepted as `GOOGLE_API_KEY` — first non-empty
       wins).

    Gemini's free tier is generous — good for trying cross-st without a
    payment method up front.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Agents
    - https://ai.google.dev/

- id: get-deepseek-key
  question: "How do I get a DeepSeek API key?"
  aliases:
    - "deepseek key"
    - "sign up deepseek"
  error_signatures: []
  answer: |
    1. Sign up at <https://platform.deepseek.com>.
    2. Add credit (DeepSeek bills per token; modest minimum top-up).
    3. API Keys → **Create**.
    4. Copy the key and paste it when `st-admin --setup` prompts for
       `DEEPSEEK_API_KEY`.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Agents

- id: error-401-auth
  question: "What does 'Error code: 401' mean?"
  aliases:
    - "auth error"
    - "authentication failed"
    - "invalid api key"
    - "unauthorized"
    - "401"
  error_signatures:
    - "Error code: 401"
    - "AuthenticationError"
    - "401 Unauthorized"
    - "invalid_api_key"
  answer: |
    **401 = the provider rejected your API key.**

    Most common causes:

    1. **Key has been rotated or revoked** — log into the provider console
       and check that the key is still active. Generate a new one if not.
    2. **Wrong env var** — Anthropic wants `ANTHROPIC_API_KEY`, OpenAI wants
       `OPENAI_API_KEY`, etc. A typo in `~/.crossenv` will silently miss.
    3. **Whitespace** — a stray newline or trailing space in the value.
    4. **Project-scoped OpenAI key, wrong project** — re-issue in the right
       project on platform.openai.com.

    Quickest check:

    ```bash
    st-admin --check-keys
    ```

    …which sends one small live request to each configured provider. It bypasses
    the response cache, so it verifies the current key but may use a small
    amount of provider quota. Missing keys are skipped.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/st-admin
    - https://github.com/crossaicore/cross-st/wiki/Troubleshooting

- id: error-no-config
  question: "Why does cross-st say no config is found?"
  aliases:
    - "missing config"
    - "no .crossenv"
    - "first run guard"
    - "require_config"
  error_signatures:
    - "No configuration found"
    - "require_config"
    - "Run st-admin --setup"
  answer: |
    Every `st-*` command (except `st-admin`, `st-man`, and `st-ask`) refuses
    to start unless **either** `~/.crossenv` exists **or** there's a `.env`
    in the current directory.

    Fix:

    ```bash
    st-admin --setup
    ```

    …adds the first key and writes `~/.crossenv`. The guard goes away
    automatically on the next `st-*` invocation.

    `--help`, `-h`, `--version`, `-V`, and `st-ask` all bypass the guard so
    you can read help text on a fresh install.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/st-admin

- id: error-shadowed-env
  question: "I added a key but cross-st doesn't see it"
  aliases:
    - "key not detected"
    - "added key still wrong"
    - "shadowed env"
    - "config not loading"
    - "ai_models"
    - "default agent wrong"
  error_signatures: []
  answer: |
    Almost always: **a project-local `.env` is shadowing `~/.crossenv`**.

    cross-st loads config in this order, **last write wins**:

    1. `~/.crossenv` (global)
    2. Repo-local `.env` (developer override) ← **wins** over `~/.crossenv`
    3. CWD `.env` (highest priority)

    If you're a developer running from a `pip install -e .` checkout and
    there's a `.env` in the checkout root with a stale key, that file wins
    silently. `st-admin` writes to `~/.crossenv`, but the developer `.env`
    still shadows it for any key present in both.

    Fix: remove the duplicated key from the developer `.env`, or run from
    a different directory. `st-admin --setup` and individual settings
    writes now print a `⚠️  Warning` naming the file that shadows.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Troubleshooting

- id: error-version-mismatch
  question: "Why am I seeing weird import errors after upgrading?"
  aliases:
    - "import error"
    - "module not found"
    - "ai_models legacy"
    - "version mismatch"
    - "cross-ai-core out of date"
  error_signatures:
    - "ImportError"
    - "ModuleNotFoundError"
    - "cannot import name"
    - "no module named cross_ai_core"
  answer: |
    cross-st pins a specific minimum `cross-ai-core` version. After you
    upgrade `cross-st` you sometimes need to upgrade the core too:

    ```bash
    pipx upgrade cross-st
    pipx runpip cross-st install --upgrade "cross-ai-core[all]"
    ```

    If that doesn't help, force-reinstall:

    ```bash
    pipx install --force cross-st
    ```

    A force-reinstall keeps your `~/.crossenv` and cache untouched.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/st-admin

- id: discourse-onboarding
  question: "How do I join the crossai.dev community?"
  aliases:
    - "discourse signup"
    - "join community"
    - "crossai.dev access"
    - "invite link"
  error_signatures: []
  answer: |
    Run:

    ```bash
    st-admin --discourse-setup
    ```

    The wizard creates an invite link for you, opens it in your browser,
    and stores the resulting Discourse credentials in `~/.crossenv`.

    **Important**: open the invite link **and** the activation email link
    in a **private/incognito window**. Discourse refuses to redeem either
    if the browser already has an active session.

    Once joined, `st-post` defaults to the safe `Test (cleared daily)`
    sandbox category. Switch later with `st-admin --discourse`.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/Discourse-Setup
    - https://crossai.dev

- id: upgrade-cross-st
  question: "How do I upgrade cross-st?"
  aliases:
    - "update cross-st"
    - "upgrade pipx"
    - "newer version"
    - "latest cross-st"
  error_signatures: []
  answer: |
    ```bash
    pipx upgrade cross-st
    ```

    Or, equivalently:

    ```bash
    st-admin --upgrade
    ```

    …which detects whether you installed via pipx, a regular venv, or an
    editable dev install, and prints the right command for your case.

    Cross-st checks PyPI for newer versions on every `st-admin` invocation
    and prints a one-line nudge if you're behind.
  see_also:
    - https://github.com/crossaicore/cross-st/wiki/st-admin
    - https://pypi.org/project/cross-st/

