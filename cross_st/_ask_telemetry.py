"""
cross_st/_ask_telemetry.py — opt-in usage telemetry for st-ask (ASK-16/17).

Architecture
------------
telemetry is **always off by default** (CROSS_ASK_TELEMETRY=off / absent).
It is switched on only by the user via:
  st-admin --ask-telemetry on   (interactive consent prompt included)
  or the first-run consent prompt inside st-ask itself.

A single function, ``send_event()``, is the only public surface.  It posts a
JSON payload to ``/api/ask-telemetry`` on the crossai.dev provisioning service
and returns silently on any error — telemetry must never break the primary flow.

Payload schema
--------------
{
  "query":      str,          # original user question (after scrubbing)
  "tier":       "pseudo"|"llm",
  "matched":    bool,         # True = an FAQ entry was returned; False = no-match
  "agent":      str|null,     # LLM tier only; null for pseudo
  "cross_st_version": str,    # e.g. "0.12.0"
  "ts":         str           # ISO-8601 UTC
}

Nothing identifying (username, API keys, paths) is ever included.
``_ask_scrub.scrub()`` is applied to the query before sending.

Server side: see discourse/server_app/app.py ``POST /api/ask-telemetry``
                and ``IMPLEMENTATION_ASK_16_17.md`` in cross-internal.

Environment variables
---------------------
CROSS_ASK_TELEMETRY         "on" / "off" (default "off")
CROSS_ASK_TELEMETRY_URL     Override endpoint (dev/test only)
PROVISION_SECRET            Bearer token (same one used by discourse_provision)
"""

import os
import threading
from datetime import datetime, timezone

# Default production endpoint
_DEFAULT_URL = "https://crossai.dev/api/ask-telemetry"

_TELEMETRY_ENV_KEY = "CROSS_ASK_TELEMETRY"
_PROVISION_SECRET_DEFAULT = "x5FZXQjpr6Do3BgHWkNJSaNb+lnIKQquNvPf4MmxScI="


def is_enabled() -> bool:
    """Return True iff the user has opted in to ask-telemetry."""
    return os.getenv(_TELEMETRY_ENV_KEY, "off").strip().lower() == "on"


def send_event(
    query: str,
    tier: str,
    matched: bool,
    agent: "str | None" = None,
) -> None:
    """Post a single telemetry event in a background thread.

    Always returns immediately. Any network / import error is silently
    swallowed — telemetry must never interrupt the user's question flow.

    Args:
        query:   The user's question, already scrubbed of sensitive data.
        tier:    "pseudo" or "llm".
        matched: True if an answer was returned, False for a no-match result.
        agent:   The agent name used (LLM tier only); None for pseudo.
    """
    if not is_enabled():
        return

    def _post() -> None:
        try:
            import requests
            from importlib.metadata import version as _pkg_version
        except ImportError:
            return

        try:
            cs_version = _pkg_version("cross-st")
        except Exception:
            cs_version = "unknown"

        url = os.getenv("CROSS_ASK_TELEMETRY_URL", _DEFAULT_URL).strip()
        secret = os.getenv("PROVISION_SECRET", _PROVISION_SECRET_DEFAULT)

        payload = {
            "query":              query,
            "tier":               tier,
            "matched":            matched,
            "agent":              agent,
            "cross_st_version":   cs_version,
            "ts":                 datetime.now(timezone.utc).isoformat(),
        }

        try:
            requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=5,
            )
        except Exception:
            pass  # silently ignore network errors, wrong URL, 4xx, etc.

    threading.Thread(target=_post, daemon=True).start()

