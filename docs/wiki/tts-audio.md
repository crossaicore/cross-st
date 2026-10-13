# TTS Audio

<!-- hand-written: do not overwrite with build_wiki.py -->

Cross can convert any research report into a spoken MP3 file.  This is
**optional** — all report generation, fact-checking, and benchmark commands
work without it.  TTS adds three commands: `st-speak`, `st-voice`, and
`st-prep --mp3`.

---

## Local Kokoro with Heart

Install the audio extra with `pipx install "cross-st[tts]"`, or run
`pip install "cross-st[tts]"` in your virtual environment. Existing pipx users
can upgrade with `pipx install --force "cross-st[tts]"`.

Add these settings to `~/.crossenv` (or the developer checkout's `.env`):

```dotenv
TTS_BACKEND=kokoro
TTS_VOICE=af_heart
```

Render a prepared report with `st-speak report.json`, or generate its audio
during preparation with `st-prep --mp3 report.json`. `st-voice sample.txt`
auditions the configured Kokoro voice. `heart` is accepted as an alias for
`af_heart`; `st-speak --voice af_heart report.json` overrides the saved voice.

Kokoro runs locally without a Piper server and ignores `TTS_HOST` and
`TTS_PORT`. Use Python 3.10–3.13. YakYak downloads about 350 MB of model and
voice data on first use into `~/.cache/yakyak/kokoro`; later renders reuse it.
Set `YAKYAK_CACHE_DIR` to choose a different cache location. MP3 output needs
FFmpeg (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Ubuntu).

For Wyoming-Piper, set `TTS_BACKEND=wyoming` (the default), a Piper voice ID,
and the server's `TTS_HOST` and `TTS_PORT`. The `st-voice --voices` and
`--curl` commands list and download Piper voices.

---

## Wyoming-Piper quick start

```bash
# 1. Install Cross with audio support
pipx install "cross-st[tts]"

# 2. Start a local Piper TTS server (Docker)
docker run -d --name wyoming-piper -p 10200:10200 \
  -v ~/piper-voices:/data \
  rhasspy/wyoming-piper --voice en_US-lessac-medium

# 3. Tell Cross where the server is (once, persists forever)
st-admin --set-tts-voice en_US-lessac-medium
# TTS_HOST and TTS_PORT default to localhost:10200

# 4. Render a story to MP3
st-speak my_topic.json    # → my_topic.mp3
```

---

## Python version support

The table below reflects **live install and import tests on macOS ARM, 2026-03-31**
(see `tests/test_tts_stack.py` to reproduce).

| Python | No-TTS | With TTS | numpy resolved |
|--------|--------|----------|----------------|
| 3.9    | ❌ | ❌ | numpy 2.2+ requires 3.10 — fails at install |
| 3.10   | ✅ | ✅ | 2.2.6 (numpy 2.3+ raised its floor to 3.11) |
| 3.11   | ✅ | ✅ | 2.2.4 (pinned in requirements.txt) |
| 3.12   | ✅ | ✅ | 2.4.4 — 18/18 packages pass import test |
| 3.13   | ✅ | ✅ | 2.4.4 — 18/18 packages pass import test |

The minimum of 3.10 is set by `numpy 2.x`, `scipy 1.15.x`, and `match`/`case`
syntax in `st-plot.py` and `st-voice.py`. Kokoro requires Python 3.10–3.13.

> **numpy note:** numpy 2.3.x raised `Requires-Python` to `>=3.11`. On Python 3.10,
> pip automatically resolves to numpy 2.2.x — no manual pinning needed.
> All numpy 2.x branches work with Cross.

---

## Install by platform

### macOS (Apple Silicon or Intel)

```bash
pipx install "cross-st[tts]"
```

`soundfile` bundles its own `libsndfile` binary on macOS — no Homebrew package
needed.  Any Python 3.10–3.13 works; use `--python` to pick a specific version:

```bash
brew install python@3.12
pipx install --python python3.12 "cross-st[tts]"
```

### Linux — Debian / Ubuntu

```bash
# System audio library (required on Linux — not bundled in the soundfile wheel)
sudo apt install libsndfile1 ffmpeg

# Install Cross with TTS
pipx install "cross-st[tts]"
```

For in-terminal voice playback in `st-voice` (the `s` key), install a player —
`afplay` is macOS-only:

```bash
sudo apt install mpv
echo "AUDIO_PLAYER=mpv" >> ~/.crossenv
```

### Linux — Fedora / RHEL

```bash
sudo dnf install libsndfile ffmpeg
pipx install "cross-st[tts]"
```

### Linux — Arch

```bash
sudo pacman -S libsndfile ffmpeg
pipx install "cross-st[tts]"
```

### Windows

Native Windows is not supported for TTS (`soundfile` has no Windows wheel and
Cross uses POSIX APIs for keyboard input).  Use **WSL2** instead:

```powershell
# PowerShell — installs WSL2 with Ubuntu
wsl --install
```

Then follow the Ubuntu instructions above inside the WSL2 terminal.

---

## Piper TTS server

Cross does not bundle a speech engine.  It connects to a locally-running
**Wyoming Piper** server via TCP.  You need to start this server once before
using any TTS command.

### Docker (recommended)

```bash
docker run -d \
  --name wyoming-piper \
  --restart unless-stopped \
  -p 10200:10200 \
  -v ~/piper-voices:/data \
  rhasspy/wyoming-piper \
  --voice en_US-lessac-medium
```

The `~/piper-voices` directory is where ONNX model files are stored.

### Native (no Docker)

```bash
pipx install wyoming-piper
wyoming-piper --voice en_US-lessac-medium --uri tcp://0.0.0.0:10200
```

See [wyoming-piper on GitHub](https://github.com/rhasspy/wyoming-piper) for
full server options.

### Configure Cross

Add to `~/.crossenv`:

```env
TTS_HOST=localhost
TTS_PORT=10200
TTS_VOICE=en_US-lessac-medium
```

Or set via `st-admin`:

```bash
st-admin --set-tts-voice en_US-lessac-medium
```

`TTS_HOST` and `TTS_PORT` default to `localhost` and `10200` when not set.

---

## Voice management

### Browse voices

```bash
st-voice --voices          # list all available en_US / en_GB voice names
```

### Download voice models

Voice ONNX files (~30–130 MB each) are fetched from Hugging Face:

```bash
st-voice --curl | bash     # download all voices
st-voice --curl | grep "lessac" | bash   # download one specific voice
```

Store model files in the directory your Piper server watches (`~/piper-voices`
in the Docker example above).

### Audition voices

```bash
st-voice sample.txt        # interactive shell
```

Keys: `v` next voice · `s` speak · `e` edit · `q` quit

### Recommended starting voices

| Voice | Quality | Style |
|-------|---------|-------|
| `en_US-lessac-medium` | Good | Neutral, clear |
| `en_US-lessac-high` | High | Same speaker, higher fidelity |
| `en_US-ryan-high` | High | Male, expressive |
| `en_US-libritts-high` | High | Natural prosody |

---

## TTS commands reference

| Command | Output |
|---------|--------|
| `st-speak my_topic.json` | `my_topic.mp3` from story 1 |
| `st-speak -s 3 my_topic.json` | MP3 from story 3 |
| `st-speak --source fact my_topic.json` | Reads fact-check report aloud |
| `st-speak --voice en_US-ryan-high my_topic.json` | One-off voice override |
| `st-prep my_topic.json --mp3` | Process text and render MP3 |
| `st-prep my_topic.json --all` | Export md + mp3 + txt + title |

---

## Without TTS

All commands except `st-speak`, `st-voice`, and `st-prep --mp3`/`--all` work
without TTS packages.

```bash
pipx install cross-st          # no TTS extras
```

Running a TTS command without the packages prints a clear message and exits:

```
Error: st-speak requires TTS packages.
Run: pip install "cross-st[tts]"  or  pipx install "cross-st[tts]"
```

---

## Troubleshooting

**`TTS host localhost:10200 is offline`**  
The Piper server is not running.  Start it (see above), then test:
```bash
nc -z localhost 10200 && echo "up" || echo "down"
```

**`ImportError` / `soundfile not found`**  
TTS packages not installed: `pip install "cross-st[tts]"`

**`libsndfile` error on Linux**  
`sudo apt install libsndfile1` (Debian/Ubuntu) — the Linux soundfile wheel
does not bundle `libsndfile` the way the macOS wheel does.

**No audio playback on Linux**  
`afplay` is macOS-only.  Install `mpv` and add `AUDIO_PLAYER=mpv` to `~/.crossenv`.

**Voice model not found**  
Download the ONNX file: `st-voice --curl | grep "your-voice" | bash`

---

## Further reading

- `README-TTS-audio.md` in the repo — full reference with deeper technical detail
- [Wyoming Piper](https://github.com/rhasspy/wyoming-piper) — TTS server docs
- [Piper voice list](https://github.com/rhasspy/piper/blob/master/VOICES.md)
- [Onboarding](Onboarding) — first-time setup guide


