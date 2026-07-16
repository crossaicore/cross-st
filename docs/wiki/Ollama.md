# Ollama (local & private AI)

**Ollama** lets Cross run open-weight models **on your own machine or LAN** instead of a cloud API. It is Cross's first **local** and first **keyless** provider (cross-ai-core 0.10.0+): no API key, no per-token billing, and — on a trusted network — **your prompts and reports never leave your hardware**.

> 🔒 **Privacy:** with an Ollama agent, generation and cross-checking happen entirely on your machine (or a machine you control on your LAN). Nothing is sent to a third-party provider.

Ollama is an **agent** like any other — see **[Agents](Agents)** for the `--agent` flag and **[AI Providers](ai-providers)** for the cloud providers.

---

## 1. Install Ollama + pull a model

```bash
# macOS
brew install ollama          # CLI, or install the Ollama.app
ollama serve &               # start the local daemon (http://localhost:11434)
ollama pull llama3.1         # download a model (one-time)
ollama list                  # see installed models
```

A small model is enough to try it out — e.g. `ollama pull qwen2.5:0.5b` (~0.4 GB) or `ollama pull llama3.2:1b`.

## 2. Add an Ollama agent

**Interactive** (`st-admin` → `a` → `m` → `a`):

```text
Agent name: ollama-llama
Provider:   ollama
Available models for ollama:      ← discovered live from your daemon
   1.   llama3.1:latest
   2.   qwen2.5:0.5b
Choice: 1
```

If the daemon isn't running (or has no models), the wizard shows the URL it queried and a hint:

```text
Available models for ollama:
   (no models found at http://localhost:11434 — is `ollama serve` running?)
    Pull one first, e.g.:  ollama pull llama3.1
```

**Non-interactive:**

```bash
st-admin --add-agent ollama-llama=ollama:llama3.1
st-admin --add-agent ollama-fast=ollama:qwen2.5:0.5b
```

## 3. Use it

```bash
st-gen --agent ollama-llama report.prompt      # generate locally
st-verdict --agent ollama-llama report.json    # interpret locally
st-cross --parallel report.json                # include ollama columns in the matrix
```

Set it as your default so `--agent` is optional:

```bash
st-admin --set-default-ai ollama-llama
```

---

## Configuration (environment variables)

Set these in `~/.crossenv` (global) or a project `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Daemon location — local or a **LAN host** |
| `OLLAMA_MODEL` | `llama3.1` | Default model when an agent has no explicit model |
| `OLLAMA_API_TOKEN` | *(none)* | Optional `Authorization: Bearer` token for a reverse-proxied daemon |
| `OLLAMA_REQUEST_TIMEOUT` | `120` | Generation timeout, seconds |
| `OLLAMA_HEALTH_CHECK_TIMEOUT` | `5` | Connectivity/discovery probe timeout, seconds |
| `OLLAMA_MAX_CONCURRENCY` | `2` | Max concurrent local calls in `st-cross`/`st-bang` (see Hardware below) |

Because Ollama is **keyless**, there is no `*_API_KEY` — an Ollama agent is always shown as available in `st-admin`, the `A`-key rotation in `st`, and the `st-cross` matrix.

---

## Remote / LAN Ollama

Run models on a beefier machine (e.g. a Mac Studio) and drive them from a laptop.

**On the host** — bind to all interfaces (Ollama defaults to `localhost` only):

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull llama3.1
```

- Allow inbound TCP on **port 11434** through the host's firewall.
- Use the host's `*.local` name (mDNS/Bonjour on the same subnet) or its static IP.

**On the client** — point Cross at the host:

```ini
# ~/.crossenv
OLLAMA_BASE_URL=http://mac-studio.local:11434
OLLAMA_MODEL=llama3.1
OLLAMA_HEALTH_CHECK_TIMEOUT=10   # a little more slack over the LAN
```

**Verify:**

```bash
ping -c2 mac-studio.local
curl -s http://mac-studio.local:11434/api/tags   # daemon up + installed models
```

If `curl` hangs or is refused: the daemon is still bound to localhost, port 11434 is firewalled, or the hostname doesn't resolve.

---

## Hardware & concurrency

Unlike cloud providers (whose limits model an API rate), Ollama's concurrency is bound by your **hardware** (RAM/VRAM). Running several models at once thrashes the machine, so Cross caps concurrent local calls at **2** by default. Tune it per machine:

```ini
# ~/.crossenv
OLLAMA_MAX_CONCURRENCY=1     # low-RAM laptop
OLLAMA_MAX_CONCURRENCY=4     # workstation with plenty of VRAM
```

- All Ollama agents share **one** rate-limit group, so two local agents (e.g. `ollama-llama` + `ollama-fast`) never exceed the cap together.
- Override for a single run with `st-cross --max-concurrency N`, or serialise with `st-cross --sequential`.

---

## Multiple local models in one matrix

Define several Ollama agents and cross-examine them side-by-side — or mix local and cloud:

```bash
st-admin --add-agent ollama-llama=ollama:llama3.1
st-admin --add-agent ollama-mistral=ollama:mistral
st-cross --parallel report.json     # both local columns + any cloud agents
st-speed report.json                # one timing row per agent
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Wizard shows "no models found" | `ollama serve` not running, or `ollama pull <model>` needed |
| "Cannot reach Ollama at …" | Daemon down, wrong `OLLAMA_BASE_URL`, or firewall blocking 11434 |
| Timed out after 120 s | Model still loading or host busy — raise `OLLAMA_REQUEST_TIMEOUT` |
| LAN host unreachable | Start with `OLLAMA_HOST=0.0.0.0`, open port 11434, check `*.local` resolves |

---

## See also

- [Agents](Agents) — the `--agent` flag, naming, resolution order
- [AI Providers](ai-providers) — the five cloud providers
- [Multi-Model](Multi-Model) — running matrices across multiple agents
- [Onboarding](Onboarding) — first-time setup
- [st-admin](st-admin) — agent management UI

