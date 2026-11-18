"""Revision identities, selection, presentation, and atomic container writes.

The persisted report body excludes the generated version footer.  Existing raw
responses and report fields survive adoption unchanged; IDs do not depend on
provider metadata or timing.  Indices returned by this module are zero-based;
``selected_indices(explicit_index=...)`` accepts the CLI's one-based index.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from uuid import uuid4

SCHEMA_VERSION = 1
_FOOTER = re.compile(r"\n*<!-- cross:report-version -->\n.*?\n<!-- /cross:report-version -->\s*$", re.S)


class RevisionError(ValueError):
    """Invalid or unsupported report revision state."""


class ConcurrentUpdateError(RevisionError):
    """The container changed since the user reviewed it."""


def _id(prefix):
    return f"{prefix}_{uuid4().hex}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def is_revisioned(container):
    return isinstance(container, dict) and "revision_schema_version" in container


def report_body(report):
    """Current saved Markdown, with plain text fallback and managed footer removed."""
    if not isinstance(report, dict):
        raise RevisionError("Report must be an object.")
    body = report.get("markdown") or report.get("text") or ""
    if not isinstance(body, str):
        raise RevisionError("Report body must be text.")
    return _FOOTER.sub("", body).strip("\r\n")


def content_digest(report_or_body):
    """SHA256 over NFC/LF body, excluding only explicitly managed version markup."""
    body = report_body(report_or_body) if isinstance(report_or_body, dict) else report_or_body
    if not isinstance(body, str):
        raise RevisionError("Report body must be text.")
    body = unicodedata.normalize("NFC", _FOOTER.sub("", body).replace("\r\n", "\n").replace("\r", "\n").strip("\n"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def container_fingerprint(container_or_bytes):
    """Hash exact file bytes, or canonical JSON when explicitly given an object."""
    raw = container_or_bytes
    if isinstance(raw, dict):
        raw = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if not isinstance(raw, bytes):
        raise TypeError("Expected bytes or a container object")
    return hashlib.sha256(raw).hexdigest()


def _positive(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _unique_objects(items, key, label):
    if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
        raise RevisionError(f"{label} must be an array of objects.")
    identifiers = [x.get(key) for x in items]
    if any(not isinstance(x, str) or not x for x in identifiers) or len(set(identifiers)) != len(identifiers):
        raise RevisionError(f"{label} identities must be non-empty and unique.")
    return dict(zip(identifiers, items))


def validate_container(container):
    """Validate additive schema, references, lineage, and stored content digests."""
    if not isinstance(container, dict):
        raise RevisionError("Container must be an object.")
    reports = container.get("story", [])
    raw = container.get("data", [])
    if not isinstance(reports, list) or any(not isinstance(x, dict) for x in reports):
        raise RevisionError("Container story must be an array of report objects.")
    if not isinstance(raw, list) or any(not isinstance(x, dict) for x in raw):
        raise RevisionError("Container data must be an array of objects.")
    if not is_revisioned(container):
        if any(k in container for k in ("revisions", "active_revision_id", "next_report_version")):
            raise RevisionError("Incomplete revision metadata: missing revision_schema_version.")
        return container
    if type(container["revision_schema_version"]) is not int or container["revision_schema_version"] != SCHEMA_VERSION:
        raise RevisionError("Unsupported revision schema; use a compatible Cross version.")
    if not reports:
        raise RevisionError("A revisioned container must contain reports.")
    by_report = _unique_objects(reports, "report_id", "Reports")
    by_revision = _unique_objects(container.get("revisions"), "id", "Revisions")
    if not isinstance(container.get("active_revision_id"), str) or container.get("active_revision_id") not in by_revision:
        raise RevisionError("Active revision does not exist.")
    versions = [r.get("report_version") for r in reports]
    if any(not _positive(x) for x in versions) or len(set(versions)) != len(versions):
        raise RevisionError("Report version numbers must be positive and unique.")
    if not _positive(container.get("next_report_version")) or container["next_report_version"] <= max(versions):
        raise RevisionError("Next report version must exceed every allocated version.")
    by_data = _unique_objects(raw, "data_id", "Raw records") if raw else {}
    memberships = []
    for revision in by_revision.values():
        members, parents = revision.get("report_ids"), revision.get("parent_report_ids")
        if not isinstance(members, list) or not members or any(not isinstance(x, str) or x not in by_report for x in members):
            raise RevisionError("Revision references missing reports.")
        if len(set(members)) != len(members):
            raise RevisionError("Revision contains duplicate report references.")
        if not isinstance(parents, list) or any(not isinstance(x, str) or x not in by_report for x in parents):
            raise RevisionError("Revision references missing parents.")
        if len(set(parents)) != len(parents) or set(parents) & set(members):
            raise RevisionError("Invalid revision parent references.")
        memberships.extend(members)
        for member in members:
            r = by_report[member]
            if r.get("revision_id") != revision["id"]:
                raise RevisionError("Report revision membership is inconsistent.")
            if any(by_report[parent]["report_version"] >= r["report_version"] for parent in parents):
                raise RevisionError("Parents must precede their successor versions.")
            expected = [by_report[parent]["report_version"] for parent in parents]
            if r.get("parent_report_versions", []) != expected:
                raise RevisionError("Report parent version labels are inconsistent.")
    if len(memberships) != len(reports) or set(memberships) != set(by_report):
        raise RevisionError("Each report must belong to exactly one revision.")
    for report in reports:
        if report.get("content_sha256") != content_digest(report):
            raise RevisionError("Report content changed outside revision tracking. Save the edited text separately, restore this container from a known snapshot, then apply the saved text with st-edit. If no snapshot exists, import the text into a new container; old verification cannot be recovered from a hash alone.")
        source = report.get("source_data_id")
        if source is not None and (not isinstance(source, str) or source not in by_data):
            raise RevisionError("Report source data does not exist.")
        if source is not None and by_data[source].get("revision_id") not in (None, report["revision_id"]):
            raise RevisionError("Report source data belongs to another revision.")
    for entry in raw:
        if entry.get("revision_id") is not None and (not isinstance(entry["revision_id"], str) or entry["revision_id"] not in by_revision):
            raise RevisionError("Raw record revision does not exist.")
    return container


def selected_indices(container, explicit_index=None):
    validate_container(container)
    reports = container.get("story", [])
    if explicit_index is not None:
        if not _positive(explicit_index) or explicit_index > len(reports):
            raise RevisionError(f"Report index must be between 1 and {len(reports)}.")
        return [explicit_index - 1]
    if not is_revisioned(container):
        return list(range(len(reports)))
    active = container["active_revision_id"]
    return [i for i, report in enumerate(reports) if report["revision_id"] == active]


def version_label(report):
    version = report.get("report_version")
    if not _positive(version):
        return ""
    parents = report.get("parent_report_versions", [])
    return f"Report v{version}" + (" · Based on " + ", ".join(f"v{x}" for x in parents) if parents else "")


def render_report(report, fmt="markdown"):
    """Render a version label without changing persisted body or human closing notes."""
    if fmt not in ("markdown", "text", "plain"):
        raise RevisionError("Report format must be markdown or text.")
    if fmt == "markdown":
        body = report_body(report)
    else:
        body = report.get("text") or report_body(report)
        body = _FOOTER.sub("", body).strip("\r\n")
    attribution = report.get("attribution")
    if isinstance(attribution, str) and attribution.strip() and not body.endswith(attribution.strip()):
        body += "\n\n" + attribution.strip()
    label = version_label(report)
    if not label:
        return body
    if fmt == "markdown":
        return f"{body}\n\n<!-- cross:report-version -->\n*{label}*\n<!-- /cross:report-version -->"
    return f"{body}\n\n{label}"


def _resolve_report(container, report_or_index):
    return container["story"][report_or_index] if isinstance(report_or_index, int) else report_or_index


def _revision(container, report):
    return next((r for r in container.get("revisions", []) if r["id"] == report.get("revision_id")), None)


def effective_brief(container, report_or_index):
    report = _resolve_report(container, report_or_index)
    revision = _revision(container, report)
    brief = revision.get("effective_brief") if revision else None
    return brief if isinstance(brief, str) and brief.strip() else None


def effective_prompt(container, report_or_index):
    """Resolve authored intent, never replay an assembled previous update request."""
    report = _resolve_report(container, report_or_index)
    revision = _revision(container, report)
    if revision and revision.get("kind") != "legacy":
        request = revision.get("change_request")
        if isinstance(request, str) and request.strip():
            return request
        if revision.get("kind") == "manual" and revision.get("parent_report_ids"):
            parent = next((r for r in container["story"] if r.get("report_id") == revision["parent_report_ids"][0]), None)
            return effective_prompt(container, parent) if parent else None
        return None
    source_id = report.get("source_data_id")
    records = container.get("data", [])
    if source_id:
        records = [entry for entry in records if entry.get("data_id") == source_id]
    elif is_revisioned(container):
        # Adoption saves resolved authored prompts explicitly where unambiguous.
        saved = report.get("authored_prompt")
        return saved if isinstance(saved, str) and saved.strip() else None
    prompts = {entry["prompt"] for entry in records if isinstance(entry.get("prompt"), str) and entry["prompt"].strip()}
    return next(iter(prompts)) if len(prompts) == 1 else None


def load_snapshot(path):
    raw = Path(path).read_bytes()
    try:
        container = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise RevisionError(f"Invalid JSON container: {exc}") from exc
    validate_container(container)
    return container, container_fingerprint(raw)


@contextmanager
def writer_lock(path):
    """Advisory process lock shared by every participating container writer."""
    lock_path = Path(str(Path(path).resolve()) + ".cross.lock")
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
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


def _preserve_history(before, after):
    if not is_revisioned(before):
        return
    if not is_revisioned(after):
        raise RevisionError("Cannot remove revision metadata.")
    if after["next_report_version"] < before["next_report_version"]:
        raise RevisionError("Cannot reuse report version numbers.")
    if len(after["story"]) < len(before["story"]) or len(after["data"]) < len(before["data"]):
        raise RevisionError("Cannot delete revision history.")
    immutable = ("report_id", "revision_id", "report_version", "source_data_id", "content_sha256", "parent_report_versions", "markdown", "text", "spoken", "title", "make", "model", "role", "attribution", "hashtags", "authored_prompt")
    for old, new in zip(before["story"], after["story"]):
        if any(old.get(key) != new.get(key) for key in immutable):
            raise RevisionError("Historical report content and identity are immutable; create a successor revision.")
    if after["data"][:len(before["data"])] != before["data"]:
        raise RevisionError("Historical raw records are immutable.")
    if after["revisions"][:len(before["revisions"])] != before["revisions"]:
        raise RevisionError("Historical revision records are immutable.")


def _replace(path, container):
    path = Path(path)
    encoded = (json.dumps(container, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            if path.exists() and hasattr(os, "fchmod"):
                os.fchmod(output.fileno(), path.stat().st_mode & 0o777)
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write(path, container, expected_fingerprint):
    """Lock, compare exact file fingerprint, validate, and atomically replace."""
    with writer_lock(path):
        previous, current = load_snapshot(path)
        if current != expected_fingerprint:
            raise ConcurrentUpdateError("Container changed; reload and review before writing.")
        validate_container(container)
        _preserve_history(previous, container)
        _replace(path, container)


def require_legacy_write(container, operation="This operation"):
    validate_container(container)
    if is_revisioned(container):
        raise RevisionError(f"{operation} does not yet support revisioned containers; use st-update or export a separate legacy container.")


def _adopt(container):
    if is_revisioned(container):
        return
    authored = [effective_prompt(container, r) for r in container["story"]]
    initial = _id("revision")
    container["revision_schema_version"] = SCHEMA_VERSION
    container["active_revision_id"] = initial
    for record in container.setdefault("data", []):
        record.setdefault("data_id", _id("data"))
        record["revision_id"] = None
    known_data_ids = {record["data_id"] for record in container["data"]}
    for index, report in enumerate(container["story"], 1):
        source_id = report.get("source_data_id")
        report.update(report_id=_id("report"), revision_id=initial, report_version=index,
                      source_data_id=source_id if source_id in known_data_ids else None, content_sha256=content_digest(report), parent_report_versions=[])
        if authored[index - 1]:
            report["authored_prompt"] = authored[index - 1]
    container["revisions"] = [{"id": initial, "kind": "legacy", "created_at": None,
        "adopted_at": _now(), "parent_report_ids": [], "report_ids": [r["report_id"] for r in container["story"]],
        "effective_brief": None, "change_request": None, "context_manifest": []}]
    container["next_report_version"] = len(container["story"]) + 1


def applied_plan(container, plan):
    """Return existing zero-based report index for exact replay, otherwise None."""
    plan_id = plan.get("id") or plan.get("plan_id")
    digest = plan.get("digest") or plan.get("plan_digest")
    for revision in container.get("revisions", []):
        if plan_id and revision.get("approved_plan_id") == plan_id:
            if revision.get("approved_plan_digest") != digest:
                raise RevisionError("A different plan already uses this plan ID.")
            target = revision["report_ids"][0]
            return next(i for i, report in enumerate(container["story"]) if report["report_id"] == target)
    return None


def commit_update(path, expected_fingerprint, parent_index, report, raw_data, plan, approval):
    """Commit a complete approved successor, adopting legacy metadata atomically."""
    if not isinstance(plan, dict) or not (plan.get("id") or plan.get("plan_id")) or not (plan.get("digest") or plan.get("plan_digest")):
        raise RevisionError("A reviewed plan ID and digest are required.")
    if not isinstance(approval, dict) or not approval:
        raise RevisionError("Explicit plan approval is required.")
    if (approval.get("plan_id") != (plan.get("id") or plan.get("plan_id"))
            or approval.get("plan_digest") != (plan.get("digest") or plan.get("plan_digest"))):
        raise RevisionError("Approval must identify the exact reviewed plan ID and digest.")
    context = plan.get("context") or {}
    if not isinstance(context, dict):
        raise RevisionError("Reviewed plan context must be an object.")
    if context.get("fingerprint") is not None and context["fingerprint"] != expected_fingerprint:
        raise RevisionError("Commit fingerprint does not match the reviewed plan.")
    if context.get("parent_index") is not None and context["parent_index"] != parent_index:
        raise RevisionError("Commit parent does not match the reviewed plan.")
    if context.get("container_path") is not None and str(Path(path).resolve()) != context["container_path"]:
        raise RevisionError("Reviewed plan belongs to a different container.")
    with writer_lock(path):
        previous, current = load_snapshot(path)
        replay = applied_plan(previous, plan)
        if replay is not None:
            return previous, replay
        if current != expected_fingerprint:
            raise ConcurrentUpdateError("Container changed since planning; review a new plan before applying.")
        if type(parent_index) is not int or parent_index < 0 or parent_index >= len(previous.get("story", [])):
            raise RevisionError("Invalid parent report index.")
        if not report_body(report).strip():
            raise RevisionError("Empty generated report; nothing saved.")
        container = deepcopy(previous)
        _adopt(container)
        parent = container["story"][parent_index]
        revision_id, report_id, data_id = _id("revision"), _id("report"), _id("data")
        new_report = deepcopy(report)
        # These fields are never inherited from the parent or accepted from AI.
        for key in ("post_id", "topic_id", "topic_url", "post_url", "discourse", "publication", "publications", "_generated_by"):
            new_report.pop(key, None)
        new_report.update(report_id=report_id, revision_id=revision_id,
            report_version=container["next_report_version"], source_data_id=data_id,
            content_sha256=content_digest(new_report), parent_report_versions=[parent["report_version"]], fact=[])
        raw = deepcopy(raw_data)
        raw.update(data_id=data_id, revision_id=revision_id)
        context = plan.get("context") or {}
        request = context.get("change_request", context.get("request", plan.get("change_request")))
        brief = context.get("effective_brief", context.get("standing_brief", plan.get("effective_brief")))
        revision = {"id": revision_id, "kind": "update", "created_at": _now(),
            "parent_report_ids": [parent["report_id"]], "report_ids": [report_id],
            "effective_brief": brief, "change_request": request,
            "context_manifest": deepcopy(context), "approved_plan_id": plan.get("id") or plan.get("plan_id"),
            "approved_plan_digest": plan.get("digest") or plan.get("plan_digest"),
            "approved_plan": deepcopy(plan), "approval": deepcopy(approval)}
        container["data"].append(raw)
        container["story"].append(new_report)
        container["revisions"].append(revision)
        container["active_revision_id"] = revision_id
        container["next_report_version"] += 1
        validate_container(container)
        _preserve_history(previous, container)
        _replace(path, container)
        return container, len(container["story"]) - 1


def activate(path, revision_id):
    container, fingerprint = load_snapshot(path)
    if not is_revisioned(container) or revision_id not in {r["id"] for r in container["revisions"]}:
        raise RevisionError("Unknown revision ID; use st-update --history.")
    container["active_revision_id"] = revision_id
    atomic_write(path, container, fingerprint)
    return container


def history(container):
    """Structured history suitable for CLI rendering, retaining physical indices."""
    validate_container(container)
    active = set(selected_indices(container))
    return [{"index": i + 1, "report_id": r.get("report_id"), "revision_id": r.get("revision_id"),
             "version": r.get("report_version"), "label": version_label(r),
             "title": r.get("title", ""), "active": i in active}
            for i, r in enumerate(container.get("story", []))]


def commit_successor(path, expected_fingerprint, parent_indices, report, raw_data=None,
                     kind="manual", change_request=None, effective_brief=None, provenance=None):
    """Save an explicit edit/fix/merge successor without fabricating an update plan."""
    if kind not in ("manual", "fix", "merge"):
        raise RevisionError("Successor kind must be manual, fix, or merge.")
    with writer_lock(path):
        previous, current = load_snapshot(path)
        if current != expected_fingerprint:
            raise ConcurrentUpdateError("Container changed while editing/generating; retain the draft and retry.")
        if (not isinstance(parent_indices, (list, tuple)) or not parent_indices
                or any(type(i) is not int or not 0 <= i < len(previous.get("story", [])) for i in parent_indices)
                or len(set(parent_indices)) != len(parent_indices)):
            raise RevisionError("Invalid parent report indices.")
        if kind != "merge" and len(parent_indices) != 1:
            raise RevisionError("Only merge revisions can have multiple parents.")
        if not report_body(report).strip():
            raise RevisionError("Empty edited report; nothing saved.")
        container = deepcopy(previous)
        _adopt(container)
        parents = [container["story"][i] for i in parent_indices]
        revision_id, report_id = _id("revision"), _id("report")
        data_id = _id("data") if raw_data is not None else None
        new_report = deepcopy(report)
        for key in ("post_id", "topic_id", "topic_url", "post_url", "discourse", "publication", "publications"):
            new_report.pop(key, None)
        new_report.update(report_id=report_id, revision_id=revision_id,
            report_version=container["next_report_version"], source_data_id=data_id,
            content_sha256=content_digest(new_report), parent_report_versions=[r["report_version"] for r in parents], fact=[])
        if raw_data is not None:
            raw = deepcopy(raw_data)
            raw.update(data_id=data_id, revision_id=revision_id)
            container["data"].append(raw)
        if effective_brief is None and len(parents) == 1:
            parent_revision = _revision(container, parents[0])
            effective_brief = parent_revision.get("effective_brief") if parent_revision else None
        container["story"].append(new_report)
        container["revisions"].append({"id": revision_id, "kind": kind, "created_at": _now(),
            "parent_report_ids": [r["report_id"] for r in parents], "report_ids": [report_id],
            "effective_brief": effective_brief, "change_request": change_request,
            "provenance": deepcopy(provenance or {}), "context_manifest": []})
        container["active_revision_id"] = revision_id
        container["next_report_version"] += 1
        validate_container(container)
        _preserve_history(previous, container)
        _replace(path, container)
        return container, len(container["story"]) - 1


def commit_manual(path, expected_fingerprint, parent_index, report, edited_field="markdown"):
    """Save a human successor and retain the nearest known authored prompt."""
    return commit_successor(path, expected_fingerprint, [parent_index], report,
                            provenance={"edited_field": edited_field})


def save_legacy(path, container):
    """Guard legacy writers at commit time against concurrent revision adoption."""
    require_legacy_write(container, "Legacy writer")
    with writer_lock(path):
        if Path(path).exists():
            current, _ = load_snapshot(path)
            require_legacy_write(current, "Legacy writer")
        _replace(path, container)
