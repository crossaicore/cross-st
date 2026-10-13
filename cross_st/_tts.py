"""Render speech with the configured YakYak backend."""
import asyncio
import os


def get_backend():
    backend = os.getenv("TTS_BACKEND", "wyoming").strip().lower()
    if backend not in {"wyoming", "kokoro"}:
        raise ValueError("TTS_BACKEND must be wyoming or kokoro")
    return backend


def get_voice(voice=None):
    backend = get_backend()
    voice = voice or os.getenv("TTS_VOICE") or (
        "af_heart" if backend == "kokoro" else "en_US-lessac-medium"
    )
    return "af_heart" if backend == "kokoro" and voice == "heart" else voice


def render_audio(text, output_file, voice=None, *, quiet=False, verbose=False,
                 host=None, port=None):
    """Write MP3 audio; return False when the Wyoming server is offline."""
    backend = get_backend()
    voice = get_voice(voice)
    try:
        if backend == "kokoro":
            from yakyak import kokoro_tts_server
        else:
            from yakyak import is_server_online, piper_tts_server
    except ImportError as error:
        raise SystemExit(
            "TTS requires YakYak (1.8 or later for Kokoro). "
            "Install it in the environment running Cross: pip install 'yakyak>=1.8'"
        ) from error

    if backend == "kokoro":
        if not quiet:
            print(f"Rendering audio with Kokoro voice {voice}…", flush=True)
        asyncio.run(kokoro_tts_server(text, output_file, "mp3", voice))
    else:
        host = host if host is not None else os.getenv("TTS_HOST")
        port = port if port is not None else os.getenv("TTS_PORT")
        if not host or not port:
            raise ValueError("Wyoming TTS requires TTS_HOST and TTS_PORT")
        port = int(port)
        if not is_server_online(host, port):
            print(f"TTS host {host}:{port} is offline")
            return False
        if verbose:
            print(f"TTS host {host}:{port} voice:{voice}")
        if not quiet:
            print(f"Rendering audio with voice {voice}…", flush=True)
        asyncio.run(piper_tts_server(host, port, text, output_file, "mp3", voice))
    if not quiet:
        print("Audio mp3 render complete")
    return True
