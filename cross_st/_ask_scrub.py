"""
Path/secret scrubber for st-ask and error breadcrumbs.
"""
import os
import re

HOME = os.path.expanduser("~")

API_KEY_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?:Bearer|Token) [a-zA-Z0-9\-_\.]+"),
    re.compile(r"[A-Z0-9]{20,40}_[A-Za-z0-9\-_]{10,}"),
]

def scrub(text):
    # Redact $HOME
    text = text.replace(HOME, "$HOME")
    # Redact API keys
    for pat in API_KEY_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text

