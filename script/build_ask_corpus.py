#!/usr/bin/env python3
"""
script/build_ask_corpus.py — Build the `st-ask` Full-LLM-tier corpus.

Reads:
  cross_st/data/support_faq.md   (hand-curated YAML FAQ — Pseudo-AI source)
  docs/wiki/*.md                  (canonical user docs)
  CHANGELOG.md                    (release history)

Writes:
  cross_st/data/support_content.md
      Concatenated user-voice corpus stamped with `# corpus_version: <X.Y.Z>`.
      This is the system prompt for `st-ask` Full-LLM-tier (≥ 1 API key).

Also validates the FAQ schema. Exits non-zero on any schema error so the
release pipeline halts before a broken FAQ ships.

Usage:
  python script/build_ask_corpus.py            # build + validate
  python script/build_ask_corpus.py --check    # validate FAQ only, no write
  python script/build_ask_corpus.py --version  # print corpus_version

Phase-1 scope (ASK-2): wiki + CHANGELOG + FAQ answers. Per-script `--help`
output is intentionally not invoked here — it duplicates what `build_wiki.py`
already renders into `docs/wiki/*.md`. Adding it would be flaky in CI (the
entry points might not be installed in the build venv). Revisit if a future
sprint shows the LLM tier needs the raw `--help` text on top of the wiki.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit(
        "ERROR: PyYAML is required.  Install with:\n"
        "  pip install pyyaml\n"
        "(it's also pinned in pyproject.toml as a runtime dep)."
    )


REPO_ROOT = Path(__file__).resolve().parent.parent
FAQ_PATH = REPO_ROOT / "cross_st" / "data" / "support_faq.md"
WIKI_DIR = REPO_ROOT / "docs" / "wiki"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
OUT_PATH = REPO_ROOT / "cross_st" / "data" / "support_content.md"

REQUIRED_KEYS = {"id", "question", "answer"}
OPTIONAL_KEYS = {"aliases", "error_signatures", "see_also"}
ALLOWED_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,64}$")


# ── Version helper ──────────────────────────────────────────────────────────

def read_corpus_version() -> str:
    """Parse `version` from pyproject.toml without importing toml at runtime."""
    try:
        import tomllib  # py3.11+
        with PYPROJECT_PATH.open("rb") as f:
            return tomllib.load(f)["project"]["version"]
    except ImportError:
        # py3.10 fallback — regex
        m = re.search(
            r'^version\s*=\s*"([^"]+)"',
            PYPROJECT_PATH.read_text(),
            re.MULTILINE,
        )
        if not m:
            sys.exit("ERROR: could not parse version from pyproject.toml")
        return m.group(1)


# ── FAQ loader + validator ──────────────────────────────────────────────────

def load_faq(path: Path = FAQ_PATH) -> list[dict]:
    """
    Read support_faq.md — a YAML document optionally preceded by a `#`
    comment header (everything before the first `---` line is dropped).

    Returns the parsed list of FAQ entry dicts.
    """
    raw = path.read_text(encoding="utf-8")

    # Strip the leading comment header. PyYAML accepts comments natively, but
    # some authors prefer a long human-readable header above the document
    # marker. We split on the first `---` on its own line.
    parts = re.split(r"^---\s*$", raw, maxsplit=1, flags=re.MULTILINE)
    yaml_text = parts[1] if len(parts) == 2 else raw

    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        sys.exit(f"ERROR: {path} is not valid YAML:\n{e}")

    if not isinstance(data, list) or not data:
        sys.exit(
            f"ERROR: {path} must be a non-empty YAML list of FAQ entries."
        )
    return data


def validate_faq(entries: list[dict]) -> list[str]:
    """Return a list of error messages; empty list = clean."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    for i, entry in enumerate(entries):
        loc = f"entry #{i + 1}"
        if not isinstance(entry, dict):
            errors.append(f"{loc}: must be a mapping, got {type(entry).__name__}")
            continue

        # Identify by id for nicer messages once we have one
        eid = entry.get("id")
        if isinstance(eid, str):
            loc = f"id={eid!r}"

        # Required keys
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            errors.append(f"{loc}: missing required key(s): {sorted(missing)}")

        # Unknown keys
        unknown = entry.keys() - ALLOWED_KEYS
        if unknown:
            errors.append(f"{loc}: unknown key(s): {sorted(unknown)}")

        # Type checks
        if "id" in entry:
            if not isinstance(eid, str) or not ID_RE.match(eid):
                errors.append(
                    f"{loc}: id must be lowercase kebab-case (matched against {ID_RE.pattern!r})"
                )
            elif eid in seen_ids:
                errors.append(f"{loc}: duplicate id {eid!r}")
            else:
                seen_ids.add(eid)

        if "question" in entry and not (
            isinstance(entry["question"], str) and entry["question"].strip()
        ):
            errors.append(f"{loc}: question must be a non-empty string")

        if "answer" in entry and not (
            isinstance(entry["answer"], str) and entry["answer"].strip()
        ):
            errors.append(f"{loc}: answer must be a non-empty string")

        for list_key in ("aliases", "error_signatures", "see_also"):
            v = entry.get(list_key)
            if v is None:
                continue
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(f"{loc}: {list_key} must be a list of strings")

    return errors


# ── Corpus assembler ────────────────────────────────────────────────────────

def _read_or_warn(path: Path, label: str) -> str | None:
    if not path.exists():
        print(f"  ⚠️  {label} not found at {path} — skipping", file=sys.stderr)
        return None
    return path.read_text(encoding="utf-8")


def assemble_corpus(entries: list[dict], version: str) -> str:
    """
    Produce the full `support_content.md` text.

    Format: a single user-voice markdown document with version stamp on
    line 1, then four labelled sections.
    """
    out: list[str] = []

    # Header / version stamp — kept on line 1 so the LLM sees it immediately.
    out.append(f"# corpus_version: {version}")
    out.append("")
    out.append("# Cross-st Help Content")
    out.append("")
    out.append(
        "> Auto-generated by `script/build_ask_corpus.py`. Do not hand-edit; "
        "edit the source files (`docs/wiki/*.md`, `CHANGELOG.md`, "
        "`cross_st/data/support_faq.md`) and re-run the build script."
    )
    out.append("")

    # 1. FAQ (highest signal — canonical answers to the questions users ask)
    out.append("---")
    out.append("")
    out.append("## Section 1 — Frequently asked questions")
    out.append("")
    for entry in entries:
        out.append(f"### {entry['question']}")
        out.append("")
        out.append(entry["answer"].rstrip())
        see_also = entry.get("see_also") or []
        if see_also:
            out.append("")
            out.append("**See also:**")
            for link in see_also:
                out.append(f"- {link}")
        out.append("")

    # 2. Wiki pages
    out.append("---")
    out.append("")
    out.append("## Section 2 — Wiki pages")
    out.append("")
    if WIKI_DIR.exists():
        wiki_files = sorted(WIKI_DIR.glob("*.md"))
        for wpath in wiki_files:
            out.append(f"### {wpath.stem}")
            out.append("")
            out.append(wpath.read_text(encoding="utf-8").rstrip())
            out.append("")
    else:
        out.append(f"_(wiki dir {WIKI_DIR} not found at build time)_")
        out.append("")

    # 3. CHANGELOG
    out.append("---")
    out.append("")
    out.append("## Section 3 — CHANGELOG")
    out.append("")
    changelog = _read_or_warn(CHANGELOG_PATH, "CHANGELOG.md")
    out.append((changelog or "_(CHANGELOG missing)_").rstrip())
    out.append("")

    return "\n".join(out) + "\n"


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(
        description="Build the st-ask Full-LLM-tier corpus from the FAQ + wiki + CHANGELOG."
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Validate the FAQ schema only; do not write support_content.md.",
    )
    p.add_argument(
        "--version",
        action="store_true",
        help="Print the corpus_version (read from pyproject.toml) and exit.",
    )
    args = p.parse_args()

    version = read_corpus_version()
    if args.version:
        print(version)
        return 0

    print(f"  → Reading {FAQ_PATH.relative_to(REPO_ROOT)}")
    entries = load_faq()
    errors = validate_faq(entries)
    if errors:
        print("  ❌  FAQ validation failed:", file=sys.stderr)
        for e in errors:
            print(f"      • {e}", file=sys.stderr)
        return 1
    print(f"  ✅  {len(entries)} FAQ entries valid")

    if args.check:
        print("  (--check passed; no corpus written)")
        return 0

    corpus = assemble_corpus(entries, version)
    OUT_PATH.write_text(corpus, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(
        f"  ✅  Wrote {OUT_PATH.relative_to(REPO_ROOT)} "
        f"({size_kb:,.1f} KB, corpus_version {version})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

