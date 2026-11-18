"""Ordinary report/raw associations and complete-pair atomic writes.

CLI positions remain ordinary array positions. The opaque raw ID only links a
prepared report to its generation; it introduces no version or ancestry model.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4


class StoreError(ValueError):
    pass


class ConcurrentWriteError(StoreError):
    pass


def validate_container(container):
    if not isinstance(container, dict):
        raise StoreError("Report container must be a JSON object.")
    if "revision_schema_version" in container or "revisions" in container:
        raise StoreError("This container uses the experimental revision format. Keep a backup; copy the desired saved report's markdown into a UTF-8 .md file, then import it with st-fetch --file COPY.md NEW_CONTAINER.json. Experimental containers are not modified by this workflow.")
    for key in ("data", "story"):
        if not isinstance(container.get(key, []), list) or any(not isinstance(item, dict) for item in container.get(key, [])):
            raise StoreError(f"Container {key} must be an array of objects.")
    ids = [item["data_id"] for item in container.get("data", []) if "data_id" in item]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise StoreError("Raw data IDs must be non-empty and unique.")
    for report in container.get("story", []):
        if "source_data_id" in report and (not isinstance(report["source_data_id"], str) or report["source_data_id"] not in ids):
            raise StoreError("A prepared report refers to a missing raw data entry.")
    return container


def fingerprint_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def load_snapshot(path):
    raw = Path(path).read_bytes()
    try:
        container = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise StoreError(f"Invalid JSON container: {exc}") from exc
    validate_container(container)
    return container, fingerprint_bytes(raw)


def require_index(container, index, key="story"):
    if type(index) is not int or not 0 <= index < len(container.get(key, [])):
        raise StoreError(f"{('Report' if key == 'story' else 'Data')} index is out of range.")
    return index


def ensure_data_id(raw):
    """Assign a pair identifier after any content-hash deduplication."""
    if "data_id" not in raw:
        raw["data_id"] = uuid4().hex
    if not isinstance(raw["data_id"], str) or not raw["data_id"]:
        raise StoreError("Raw data ID must be non-empty text.")
    return raw["data_id"]


def same_generation(left, right):
    """Exact generation equality excluding timing and storage identifiers."""
    ignored = {"timing", "data_id", "md5_hash"}
    return ({key: value for key, value in left.items() if key not in ignored}
            == {key: value for key, value in right.items() if key not in ignored})


def link_new_report(container, raw, report):
    """Link a new report without making an existing report share its raw pair.

    Producers may deduplicate responses before preparing reports. If another
    report already owns that response, retain a complete independent raw copy.
    The supplied raw entry must already be in the container.
    """
    index = next((i for i, item in enumerate(container.get("data", [])) if item is raw), None)
    if index is None:
        raise StoreError("Cannot link a report to unsaved raw data.")
    owners = [item for i, item in enumerate(container.get("story", []))
              if item is not report and raw_index(container, i) == index]
    data_id = ensure_data_id(raw)
    for owner in owners:
        owner["source_data_id"] = data_id
    if owners:
        raw = deepcopy(raw)
        raw["data_id"] = uuid4().hex
        container["data"].append(raw)
        index = len(container["data"]) - 1
    report["source_data_id"] = raw["data_id"]
    return index


def _matches_prepared_content(raw, report):
    """Recognize exact saved content, using only local response parsing."""
    content = raw.get("markdown") or raw.get("text")
    if not isinstance(content, str) or not content.strip():
        try:
            from ai_handler import get_content_auto, get_data_content
            response = raw.get("gen_response")
            if isinstance(response, dict) and response.get("_make"):
                content = get_content_auto(response)
            else:
                content = get_data_content(raw.get("make"), raw)
        except Exception:
            return False
    if not isinstance(content, str) or not content.strip():
        return False
    from mmd_branding import get_tagline_for_reading
    from mmd_process_report import (remove_story_break, remove_hashtags,
                                    remove_markdown, clean_newlines_preserve_paragraphs)
    markdown = remove_story_break(content)
    attribution = get_tagline_for_reading(raw.get("make"), raw.get("model"))
    # Use the current preferred source field, never stale text beneath edited
    # Markdown. No whitespace stripping or fuzzy matching is safe here.
    if report.get("markdown"):
        return report["markdown"] in (content, markdown, markdown + "\n\n" + attribution)
    plain = clean_newlines_preserve_paragraphs(remove_markdown(remove_hashtags(markdown)))
    return bool(report.get("text")) and report["text"] in (content, plain, plain + "\n\n" + attribution)


def raw_index(container, report_index, required=False):
    """Resolve an explicit link or a uniquely provable legacy association."""
    validate_container(container)
    require_index(container, report_index)
    report = container["story"][report_index]
    data = container.get("data", [])
    link = report.get("source_data_id")
    if link:
        return next(i for i, raw in enumerate(data) if raw.get("data_id") == link)
    if len(data) == 1 and len(container["story"]) == 1:
        return 0
    matches = [i for i, raw in enumerate(data) if _matches_prepared_content(raw, report)]
    if len(matches) == 1:
        return matches[0]
    if required:
        raise StoreError("Cannot identify this report's raw data entry safely. No array-position or model-name guess was made. Keep a backup and import the saved Markdown into a separate container before updating/removing this ambiguous legacy pair.")
    return None


def authored_prompt(container, report_index):
    index = raw_index(container, report_index)
    if index is not None:
        raw = container["data"][index]
        for key in ("update_request", "authored_prompt", "prompt"):
            if isinstance(raw.get(key), str) and raw[key].strip():
                return raw[key]
    value = container["story"][report_index].get("authored_prompt")
    if isinstance(value, str) and value.strip():
        return value
    # A common authored request is useful even when legacy raw/report pairs
    # cannot be identified. This does not establish a raw-data association.
    prompts = [raw.get("prompt") for raw in container.get("data", [])]
    if prompts and all(isinstance(value, str) and value.strip() for value in prompts):
        if len(set(prompts)) == 1:
            return prompts[0]
    return None


def update_request(container, report_index):
    index = raw_index(container, report_index)
    if index is None:
        return None
    value = container["data"][index].get("update_request")
    return value if isinstance(value, str) and value.strip() else None


def has_updates(container):
    return bool(container.get("_st_update")) or any(
        isinstance(raw.get("update_request"), str) and raw["update_request"].strip()
        for raw in container.get("data", []))


@contextmanager
def writer_lock(path):
    lock_path = Path(str(Path(path).resolve()) + ".cross.lock")
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replace(path, container):
    path = Path(path)
    payload = (json.dumps(container, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            if path.exists() and hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _check_current(path, expected_fingerprint):
    if Path(path).exists():
        current, fingerprint = load_snapshot(path)
        if fingerprint != expected_fingerprint:
            raise ConcurrentWriteError("Container changed while preparing the result; nothing was saved. Reload it and retry.")
        return current
    if expected_fingerprint is not None:
        raise ConcurrentWriteError("Container was removed while preparing the result; nothing was saved.")
    return {"data": [], "story": []}


def save_snapshot(path, container, expected_fingerprint):
    """Atomic CAS for ordinary command mutations; None means create-only."""
    validate_container(container)
    with writer_lock(path):
        previous = _check_current(path, expected_fingerprint)
        if has_updates(previous):
            container = deepcopy(container)
            container["_st_update"] = previous.get("_st_update") or True
        _replace(path, container)


def _exclusive_raw(container, index):
    target = raw_index(container, index, required=True)
    if sum(raw_index(container, i) == target for i in range(len(container.get("story", [])))) > 1:
        raise StoreError("Several reports share this raw data entry; refusing to replace or remove their shared generation.")
    return target


def commit_update(path, expected_fingerprint, source_index, raw, report, request,
                  summary=None, target_index=None):
    """Append or replace a fully prepared pair, preserving every unrelated entry."""
    if not isinstance(request, str) or not request.strip():
        raise StoreError("The update request is empty; nothing saved.")
    if not isinstance(raw, dict) or not isinstance(report, dict):
        raise StoreError("A complete raw-data/report pair is required.")
    body = report.get("markdown") or report.get("text")
    if not isinstance(body, str) or not body.strip():
        raise StoreError("Generated report is empty; nothing saved.")
    with writer_lock(path):
        current = _check_current(path, expected_fingerprint)
        require_index(current, source_index)
        replace_raw = None
        if target_index is not None:
            require_index(current, target_index)
            if not has_updates(current):
                raise StoreError("The first update must append; apply the first-call --iterate rule before saving.")
            replace_raw = _exclusive_raw(current, target_index)
        container = deepcopy(current)
        # Keep safely available authored intent with existing prepared reports
        # before a new request makes a formerly common legacy prompt differ.
        for index, existing in enumerate(container.get("story", [])):
            prompt = authored_prompt(current, index)
            if prompt and not existing.get("authored_prompt"):
                existing["authored_prompt"] = prompt
            # New generated content may equal an earlier raw response. Capture
            # every provable association before that can make it ambiguous.
            original_raw = raw_index(current, index)
            if original_raw is not None:
                existing["source_data_id"] = ensure_data_id(container["data"][original_raw])
        raw = deepcopy(raw)
        report = deepcopy(report)
        raw["data_id"] = (ensure_data_id(container["data"][replace_raw])
                          if replace_raw is not None else uuid4().hex)
        raw["update_request"] = request
        raw["prompt"] = request
        if summary is not None:
            raw["update_summary"] = deepcopy(summary)
        report["source_data_id"] = raw["data_id"]
        report["authored_prompt"] = request
        if isinstance(raw.get("base_prompt"), str):
            report["base_prompt"] = raw["base_prompt"]
        report["fact"] = []
        report["_generated_by"] = "st-update"
        for key in ("segments", "segment", "post_id", "topic_id", "post_url", "topic_url", "discourse", "publication", "publications", "mp3_url", "audio_file", "pdf_file"):
            report.pop(key, None)
        if target_index is None:
            container.setdefault("data", []).append(raw)
            container.setdefault("story", []).append(report)
            target_index = len(container["story"]) - 1
        else:
            from _report_content import archive_publication
            archive_publication(container, container["story"][target_index])
            container["data"][replace_raw] = raw
            container["story"][target_index] = report
        container["_st_update"] = True
        validate_container(container)
        _replace(path, container)
        return container, target_index


def remove_pair(container, index):
    """Return a copy with one report and its reliably associated raw entry removed."""
    validate_container(container)
    require_index(container, index)
    result = deepcopy(container)
    from _report_content import archive_publication
    archive_publication(result, result["story"][index])
    if has_updates(container):
        result["_st_update"] = container.get("_st_update") or True
    if container.get("data"):
        data_index = _exclusive_raw(container, index)
        del result["data"][data_index]
    del result["story"][index]
    validate_container(result)
    return result


def remove_report(path, index, expected_fingerprint=None):
    current, fingerprint = load_snapshot(path)
    if expected_fingerprint is not None and expected_fingerprint != fingerprint:
        raise ConcurrentWriteError("Container changed before removal; reload and retry.")
    result = remove_pair(current, index)
    save_snapshot(path, result, fingerprint)
    return result
