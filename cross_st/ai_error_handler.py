# ai_error_handler.py — compatibility shim
# Source of truth: cross-ai-core package (cross_ai_core.ai_error_handler)
from cross_ai_core.ai_error_handler import *   # noqa: F401, F403
from cross_ai_core.ai_error_handler import (   # explicit for IDE / type checkers
    handle_api_error,
    is_quota_error,
    is_rate_limit_error,
    is_transient_error,
    get_error_type,
    retry_with_backoff,
    CrossAIError,
    QuotaExceededError,
    RateLimitError,
    TransientError,
)

def write_error_breadcrumb(exception, script):
    """
    Appends a scrubbed error breadcrumb to ~/.cross_api_cache/last_error.json (max 5 entries).
    """
    import os, json, time
    try:
        from cross_st._ask_scrub import scrub
    except ImportError:
        # fallback: no scrubbing
        def scrub(x): return x
    CACHE_DIR = os.path.expanduser("~/.cross_api_cache")
    LAST_ERROR = os.path.join(CACHE_DIR, "last_error.json")
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(LAST_ERROR, "r") as f:
            data = json.load(f)
    except Exception:
        data = []
    if not isinstance(data, list):
        data = []
    entry = {
        "ts": int(time.time()),
        "exception_type": type(exception).__name__,
        "message": scrub(str(exception)),
        "script": script,
    }
    data.append(entry)
    data = data[-5:]
    with open(LAST_ERROR, "w") as f:
        json.dump(data, f, indent=2)
