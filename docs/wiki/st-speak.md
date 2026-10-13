# st-speak — Render a report into spoken audio (MP3)

Renders a report as an MP3 audio file using local Kokoro or a Wyoming-Piper server. Requires the TTS extra to be installed.

**Run after:** `st-prep`  ·  **Run before:** `st-post`

## Kokoro setup

Set `TTS_BACKEND=kokoro` and `TTS_VOICE=af_heart` in your Cross config to use
Heart locally. Kokoro requires YakYak 1.8+, Python 3.10–3.13, and FFmpeg for
MP3 output. The first render downloads about 350 MB of assets. See
[TTS Audio](tts-audio) for installation and Wyoming-Piper setup.

## Examples

```bash
st-speak subject.json               # render story 1 → subject.mp3
st-speak -s 3 subject.json          # render story 3
st-speak --source fact subject.json # read the fact-check report aloud
st-speak --voice en_US-ryan-high subject.json  # override voice for this render
```

**Options:** `-s`  `story`  `--source`  `{text,fact}`  `--voice`  `model`  `-v`  `-q`

**Related:** [st-voice](st-voice) · [st-post](st-post) · [TTS Audio](tts-audio)

---

## For developers

Requires `pipx install 'cross-st[tts]'`. Uses `_tts.py` to select Kokoro or Wyoming-Piper from `TTS_BACKEND`. Only Wyoming-Piper needs `TTS_HOST` and `TTS_PORT`. Exits cleanly with an error message if TTS dependencies are missing.

## Additional current options

- `-s`, `--story`: Story to convert (integer), default 1
- `-v`, `--verbose`: Enable verbose output, default is verbose
- `-q`, `--quiet`: Enable minimal output
