"""Revision-aware adapters used by the existing command-line tools."""
from pathlib import Path

from _report_revisions import (
    ConcurrentUpdateError, RevisionError, atomic_write, content_digest,
    is_revisioned, load_snapshot, selected_indices, validate_container,
)


def guard_legacy_path(path, operation):
    """Reject an unsupported mutation before invoking editors, providers or IO."""
    target = Path(path).with_suffix('.json')
    if target.exists():
        container, _ = load_snapshot(target)
        if is_revisioned(container):
            raise RevisionError(
                f'{operation} does not yet support revisioned containers. '
                'Use st-update to create a reviewed successor; the container was not changed.'
            )


def single_index(container, explicit=None):
    """Return a one-based selection; legacy default remains report one."""
    if not is_revisioned(container) and explicit is None:
        explicit = 1
    indices = selected_indices(container, explicit)
    if len(indices) != 1:
        raise RevisionError('Several active reports are available; select one with -s N.')
    return indices[0] + 1


def mutate_metadata(path, callback):
    """Apply metadata changes with a shared CAS transaction and bounded retries."""
    for _ in range(20):
        container, fingerprint = load_snapshot(path)
        result = callback(container)
        try:
            atomic_write(path, container, fingerprint)
            return result
        except ConcurrentUpdateError:
            continue
    raise ConcurrentUpdateError('Container remained busy; retry the operation.')


def append_fact(path, index, expected_digest, fact, segments, expected_report_id=None):
    """Bind checker results to the exact report checked, preserving other writers."""
    def apply(container):
        validate_container(container)
        report = container['story'][index]
        if (content_digest(report) != expected_digest
                or (expected_report_id is not None and report.get('report_id') != expected_report_id)):
            raise RevisionError('Report changed during checking; stale findings were not saved.')
        if is_revisioned(container):
            fact['report_id'] = report['report_id']
            fact['content_sha256'] = report['content_sha256']
        facts = report.setdefault('fact', [])
        duplicate = next((item for item in facts if item.get('md5_hash') == fact.get('md5_hash')), None)
        if duplicate is None:
            facts.append(fact)
        elif is_revisioned(container):
            # A fresh check may reproduce an adopted legacy finding. Bind the
            # newly checked result instead of perpetually retaining an unbound
            # duplicate that resume detection can never recognize as complete.
            duplicate.update(fact)
        report['segments'] = segments
    mutate_metadata(path, apply)


def clear_selected_facts(path, indices, expected_reports=None):
    def apply(container):
        validate_container(container)
        count = 0
        for index in indices:
            report = container['story'][index]
            if expected_reports and (report.get('report_id'), report.get('content_sha256')) != expected_reports[index]:
                raise RevisionError('Selected report changed before clearing findings; nothing was saved.')
            count += len(report.get('fact') or [])
            report['fact'] = []
        return count
    return mutate_metadata(path, apply)
