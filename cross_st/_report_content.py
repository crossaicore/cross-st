"""Content-bound edits, checks, and publication receipts for ordinary reports."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from _report_store import ConcurrentWriteError, StoreError, load_snapshot, writer_lock, _replace
from mmd_branding import get_speaking_tagline, get_tagline_for_reading
from mmd_for_speaking import for_speaking
from mmd_process_report import clean_newlines_preserve_paragraphs, get_hashtags, remove_hashtags, remove_markdown


def content_identity(report):
    """Exclude attached checks and exports, which may be saved concurrently."""
    fields = ("source_data_id", "make", "model", "title", "markdown", "text", "spoken")
    return hashlib.sha256(json.dumps({key: report.get(key) for key in fields},
                                    sort_keys=True).encode()).hexdigest()


def current_report(container, index, expected_identity):
    reports = container.get("story", [])
    if not 0 <= index < len(reports) or content_identity(reports[index]) != expected_identity:
        raise ConcurrentWriteError("Selected report changed or moved while preparing the result; nothing was attached. Reload and retry.")
    return reports[index]


def edited_report(report, field, value):
    """Keep the saved raw response as provenance; edit the prepared report in place."""
    result = deepcopy(report)
    result[field] = value
    if field in ("markdown", "text"):
        # Text edits become the saved body too, so future updates see the edit.
        if field == "text":
            result["markdown"] = value
        plain = clean_newlines_preserve_paragraphs(remove_markdown(remove_hashtags(result["markdown"])))
        result["text"] = plain
        spoken_body = result["markdown"]
        tags = {result.get("attribution"),
                get_tagline_for_reading(result.get("make"), result.get("model"))}
        for tag in tags:
            if tag:
                spoken_body = re.sub(r"(?m)^" + re.escape(tag) + r"[ \t]*(?:\r?\n|$)", "", spoken_body)
        spoken_plain = clean_newlines_preserve_paragraphs(remove_markdown(remove_hashtags(spoken_body)))
        result["spoken"] = for_speaking(spoken_plain, False) + "\n\n" + get_speaking_tagline(result.get("make"), result.get("model"))
        result["hashtags"] = get_hashtags(result["markdown"])
    if field in ("markdown", "text", "title"):
        result["fact"] = []
        result.pop("segments", None)
    for key in ("topic_id", "post_id", "post_url", "topic_url", "mp3_url", "mp3", "audio_file", "pdf_file", "publication", "publications"):
        result.pop(key, None)
    result.pop("md5_hash", None)
    result["md5_hash"] = hashlib.md5(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def save_fact(path, index, expected_identity, fact, segments):
    """Merge independent checkers, rejecting results for edited/replaced reports."""
    with writer_lock(path):
        container, _ = load_snapshot(path)
        report = current_report(container, index, expected_identity)
        facts = report.setdefault("fact", [])
        if any(old.get("md5_hash") == fact.get("md5_hash") for old in facts):
            return False
        if report.get("segments") and report["segments"] != segments:
            raise ConcurrentWriteError("Report segmentation changed while checking; reload and retry.")
        report["segments"] = segments
        facts.append(fact)
        _replace(path, container)
        return True


def archive_publication(container, report):
    """Keep a known remote copy independent from subsequent local edits."""
    url = report.get("post_url")
    if not url:
        return
    parsed = urlsplit(url)
    receipt = {"title": report.get("title"), "post_url": url,
               "site_url": f"{parsed.scheme}://{parsed.netloc}",
               "topic_id": report.get("topic_id"), "mp3_url": report.get("mp3_url", "")}
    receipts = container.setdefault("_publications", [])
    if not any(old.get("post_url") == url for old in receipts):
        receipts.append(receipt)


def published_title_exists(container, site_url, title):
    site_url = site_url.rstrip("/")
    return any(receipt.get("site_url", "").rstrip("/") == site_url
               and receipt.get("title") == title
               for receipt in container.get("_publications", []))


def save_publication(path, index, expected_identity, receipt):
    """Retain remote success even if the selected local content changed."""
    receipt = dict(receipt, published_at=datetime.now(timezone.utc).isoformat())
    try:
        with writer_lock(path):
            container, _ = load_snapshot(path)
            container.setdefault("_publications", []).append(receipt)
            try:
                report = current_report(container, index, expected_identity)
            except ConcurrentWriteError:
                attached = False
            else:
                archive_publication(container, report)
                report.update({key: receipt[key] for key in ("topic_id", "post_url", "mp3_url")})
                attached = True
            _replace(path, container)
            return attached, None
    except (OSError, ValueError):
        # Never lose the only local record of a successful remote operation.
        try:
            directory = Path(path).resolve().parent / ".cross-receipts"
            directory.mkdir(exist_ok=True)
            recovery = directory / f"{uuid4().hex}.receipt"
            recovery.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            return False, recovery
        except OSError as exc:
            raise StoreError(f"Post succeeded: {receipt.get('post_url')}. Neither the container nor a recovery receipt could be saved: {exc}. Keep the post URL.") from exc
