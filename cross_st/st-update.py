#!/usr/bin/env python3
"""st-update — Research, review, and apply updates to an existing report.

Start with a report you already have in a .json container. Describe what should
change; Cross proposes an update plan, waits for your approval, then saves a new
report version in that SAME file. Earlier versions and their fact checks remain.

## Start here

    st-update report.json --update-details

1. Cross selects the active report, or asks which report to update.
2. Your configured editor opens. Write the changes you want, then save and close.
   For example: "Add these new pilot results: 12 tasks completed, 3 failed.
   Replace the earlier counts. Keep the headings and flag missing failure reasons."
3. The AI analyzes your request and supplied material, then shows PROPOSED
   changes. The report has not been changed at this point.
4. Type Approve to generate the revision, Details or Summary to inspect the
   plan, Revise to edit your request and get a new plan, or Cancel to stop.
5. After approval, Cross saves a new version and makes it the active report.
   Read it with: st-cat --markdown report.json

Research here means analyzing material you supply, including facts written in
these instructions. It does not search the web. Add local source files with
--evidence FILE (repeatable). The AI is asked to preserve your report's wording,
headings, tables, and manual edits except where the approved changes require it.

The normal path makes one planning call, then one generation call after approval.
Changing summary views makes no extra call. Revising the request makes a new
planning call. API cost depends on the selected agent and inputs.

## Common workflows

    # Use the concise review (default); enter your request in the editor.
    st-update report.json

    # Read an existing change request and attach new evidence; still approve
    # interactively. changes.prompt contains UPDATE instructions, not the report.
    st-update report.json --prompt changes.prompt --evidence findings.md

    # Research and inspect proposed changes now; leave the report unchanged.
    st-update report.json --prompt changes.prompt --update-details --review-only

    # Later: approve the exact saved plan using the path printed by review-only.
    st-update report.json --apply-plan PATH_TO_SAVED_PLAN

    # Check local inputs without making any AI call or saving a plan.
    st-update report.json --prompt changes.prompt --dry-run

## Versions and checking

    st-update report.json --history                  # list versions and IDs
    st-update report.json -s 1                       # branch from report index 1
    st-update report.json --activate REVISION_ID      # return to an older version
    st-update report.json --update-details --check   # verify the new report too

Fact-checking is OFF by default. --check verifies only the new report after it
is saved. --with-facts instead includes earlier findings as input; it runs no
checks. Generated versions start unverified and are not automatically published.

--review-only makes a planning call and saves a .plan file beside the container
in .cross-update/. --dry-run makes no AI calls and writes nothing. Scripts must
use --prompt with --review-only, then --apply-plan after review; --prompt alone
does not bypass approval. Changed containers or changed saved plans are rejected.

Use --brief FILE for lasting audience/scope requirements; use --base-prompt FILE
only to supply missing baseline intent. --recover-attempt FILE retries saving a
retained generated response after a preparation/write failure without another
AI generation call. The saved plan and current inputs are checked again.

Full walkthrough and worked examples: docs/wiki/st-update.md and
docs/wiki/st-update-examples.md in the cross-st checkout.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from mmd_startup import load_cross_env, require_config
from cli_agent import add_agent_arg
import _report_revisions as revisions
import _update_plan as engine


def parser_for_cli():
    overview, workflows = __doc__.split("## Common workflows", 1)
    parser = argparse.ArgumentParser(
        prog="st-update", formatter_class=argparse.RawDescriptionHelpFormatter,
        description=overview.strip().replace("## ", ""),
        epilog=("Common workflows" + workflows).replace("## ", ""))
    parser.add_argument("json_file", type=Path, metavar="FILE.json", help="Existing report container; the new version is saved in this same file")
    parser.add_argument("-s", "--story", dest="index", type=int, help="Baseline report index (one-based)")
    add_agent_arg(parser)
    parser.add_argument("--prompt", type=Path, help="Read UPDATE instructions from FILE; approval is still required")
    parser.add_argument("--brief", type=Path, help="Supply persistent purpose, audience, and constraints for future updates")
    parser.add_argument("--base-prompt", type=Path, help="Supply missing baseline intent")
    parser.add_argument("--evidence", type=Path, action="append", default=[], help="Local UTF-8 evidence (repeatable)")
    parser.add_argument("--with-facts", action="store_true", help="Include existing baseline findings without new checks")
    parser.add_argument("--check", action="store_true", help="Cross-check only the newly saved report")
    parser.add_argument("--as-of", type=date.fromisoformat, help="Requested date (YYYY-MM-DD); does not fetch evidence")
    views = parser.add_mutually_exclusive_group()
    views.add_argument("--update-summary", action="store_true", help="Show concise proposed changes (default)")
    views.add_argument("--update-details", action="store_true", help="Show every planned change, reason, source, and uncertainty")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--draft-only", action="store_true", help="Save/edit a request without AI calls")
    modes.add_argument("--dry-run", action="store_true", help="Validate local inputs only; requires --prompt; no AI calls or writes")
    modes.add_argument("--review-only", action="store_true", help="Make a planning call, display/save proposed changes, and stop before generation")
    modes.add_argument("--apply-plan", type=Path, help="Approve and apply an exact previously saved plan")
    modes.add_argument("--recover-attempt", type=Path, help="Approve and save a retained response without another AI call")
    modes.add_argument("--history", action="store_true", help="List revisions without AI calls")
    modes.add_argument("--activate", metavar="REVISION_ID", help="Select an existing revision without generation")
    parser.add_argument("--no-spell", action="store_true", help="Skip optional Aspell in the editor")
    parser.add_argument("--no-cache", action="store_true", help="Bypass AI cache; does not refresh evidence")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress progress, retaining review and approval")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show additional operational information")
    return parser


def validate_options(parser, args, interactive):
    inputs = (args.index is not None or args.agent or args.prompt or args.base_prompt
              or args.brief or args.evidence or args.with_facts or args.as_of)
    summary = args.update_summary or args.update_details
    if (args.history or args.activate) and (inputs or summary or args.check or args.no_cache or args.no_spell):
        parser.error("--history/--activate cannot be combined with update options")
    if (args.apply_plan or args.recover_attempt) and (inputs or summary or args.no_spell):
        parser.error("Saved-plan application/recovery uses saved inputs; do not supply overrides or summary selectors")
    if (args.draft_only or args.dry_run) and summary:
        parser.error("summary selectors require research/review")
    if (args.draft_only or args.review_only) and args.check:
        parser.error("--check requires applying a report update")
    if args.dry_run and not args.prompt:
        parser.error("--dry-run requires --prompt")
    local_mode = args.history or args.activate or args.dry_run or args.apply_plan or args.recover_attempt
    if not interactive and not local_mode:
        if not args.prompt or not (args.review_only or args.draft_only):
            parser.error("non-interactive use requires --prompt --review-only, then --apply-plan FILE after review")


def read_text(path):
    return path.read_text(encoding="utf-8") if path else None


def edit_request(container_path, initial, args):
    fd, filename = tempfile.mkstemp(prefix=container_path.stem + ".update-", suffix=".prompt", dir=container_path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(initial)
    path = Path(filename)
    print(f"Update request: {path}")
    if not sys.stdin.isatty():
        return initial, path
    editor = shlex.split(os.environ.get("EDITOR", "vi"))
    if not editor or subprocess.run([*editor, str(path)]).returncode:
        raise ValueError(f"Editor failed; request retained at {path}")
    if not args.no_spell:
        spell = shutil.which("aspell")
        if spell:
            subprocess.run([spell, "check", str(path)], check=False)
        elif not args.quiet:
            print("Spell check skipped: 'aspell' is not installed. Use --no-spell to disable this check.")
    return read_text(path).strip(), path


def choose_report(container, explicit, interactive):
    indices = revisions.selected_indices(container, explicit)
    if len(indices) == 1:
        return indices[0]
    if not indices:
        raise ValueError("No report is available to update")
    if not interactive:
        raise ValueError("Several baseline reports are available; choose one with -s N")
    for index in indices:
        report = container["story"][index]
        print(f"  {index + 1}: {report.get('title', '(untitled)')} — {report.get('make', 'unknown')} {report.get('model', '')}")
    answer = input("Baseline report index (blank cancels): ").strip()
    if not answer:
        raise EOFError
    chosen = int(answer) - 1
    if chosen not in indices:
        raise ValueError("Choose one of the displayed baseline indices, or restart with -s N for history")
    return chosen


def print_history(container):
    revisions.validate_container(container)
    active = container.get("active_revision_id")
    if not revisions.is_revisioned(container):
        print("Legacy container — revision history starts on the first successful update.")
    for index, report in enumerate(container.get("story", []), 1):
        mark = " * active" if report.get("revision_id") == active and active else ""
        print(f"{index}: {revisions.version_label(report) or 'untracked'} — {report.get('title', '(untitled)')}"
              f"  revision={report.get('revision_id', 'untracked')}{mark}")


def already_applied(container, plan):
    return revisions.applied_plan(container, plan)


def run_checks(path, index, args):
    command = [sys.executable, str(Path(__file__).with_name("st-cross.py")),
               "--skip-gen", "--story", str(index + 1), str(path)]
    if args.quiet:
        command.append("--quiet")
    outcome = subprocess.run(command, check=False).returncode
    if outcome:
        print(f"Report saved; verification failed or was incomplete. Retry: st-cross --skip-gen --story {index + 1} {shlex.quote(str(path))}", file=sys.stderr)
        return 3
    return 0


def run(args):
    path = args.json_file.expanduser().resolve()
    container, fingerprint = revisions.load_snapshot(path)
    if args.history:
        print_history(container)
        return 0
    if args.activate:
        revisions.activate(path, args.activate)
        print(f"Active revision: {args.activate}")
        return 0
    attempt = None
    if args.apply_plan or args.recover_attempt:
        if args.recover_attempt:
            attempt = engine.load_attempt(args.recover_attempt)
            artifact = attempt["plan"]
        else:
            artifact = engine.load_plan(args.apply_plan)
        if str(path) != artifact["context"]["container_path"]:
            raise ValueError("Saved plan belongs to a different container")
        existing = already_applied(container, artifact)
        if existing is not None:
            print(f"Plan already applied: report index {existing + 1}; no new revision.")
            return run_checks(path, existing, args) if args.check else 0
        engine.validate_freshness(artifact, path)
        artifact_path = args.apply_plan or args.recover_attempt
        approval_method = "recover-attempt" if attempt else "apply-plan"
    else:
        index = choose_report(container, args.index, sys.stdin.isatty())
        request = read_text(args.prompt)
        if not args.prompt:
            request, _ = edit_request(path, "", args)
        elif args.draft_only:
            # Copy supplied briefs into unique drafts without altering the original.
            request, _ = edit_request(path, request, args)
        if args.draft_only:
            return 0
        if not request or not request.strip():
            print("No changes requested; no update made.")
            return 0
        context = engine.build_context(container, index, request.strip(), container_path=str(path),
                                       fingerprint=fingerprint, evidence=args.evidence,
                                       base_prompt=read_text(args.base_prompt), standing_brief=read_text(args.brief), with_facts=args.with_facts,
                                       as_of=args.as_of.isoformat() if args.as_of else None)
        from ai_handler import get_default_ai
        agent = args.agent or get_default_ai()
        engine.resolve_agent_identity(agent)
        budget = engine.check_context_budget(context)
        if not args.quiet or args.dry_run:
            print(f"Baseline: report index {index + 1}; supplied evidence: {len(args.evidence)} file(s).")
            print("Inputs: selected report, available authored prompt/standing brief, request, supplied evidence"
                  + (", existing findings." if args.with_facts else "."))
            print(f"Context estimate: {budget['estimated_input_tokens']} conservative input tokens + "
                  f"{budget['output_reserve']} output reserve; configured ceiling {budget['context_limit']} "
                  "(not a discovered model limit).")
            if args.with_facts and context.get("excluded_facts"):
                print(f"Excluded {context['excluded_facts']} earlier findings with mismatched content bindings.")
            if args.with_facts and not context.get("facts"):
                print("No usable earlier findings; continuing without fact context.")
            print("AI operations: 1 planning call; 1 report-generation call after approval"
                  + ("; optional cross-check calls for the new report." if args.check else "; no fact checks."))
            print("Research uses supplied material. Actual API cost depends on the selected agent and input size.")
        if args.dry_run:
            return 0
        while True:
            artifact = engine.research(context, agent, use_cache=not args.no_cache, quiet=args.quiet, verbose=args.verbose)
            artifact_path = engine.save_plan(artifact)
            print(engine.render_plan(artifact, details=args.update_details))
            print(f"Saved update plan: {artifact_path}")
            if args.review_only:
                return 0
            if not artifact["plan"]["changes"]:
                print("No applicable changes; no report generated.")
                return 0
            while True:
                answer = input("Approve / Details / Summary / Revise request / Cancel: ").strip().lower()
                if answer in ("d", "details", "s", "summary"):
                    print(engine.render_plan(artifact, details=answer in ("d", "details")))
                elif answer in ("a", "approve"):
                    if artifact["plan"].get("questions"):
                        print("Resolve the listed questions by revising the request before approval.")
                        continue
                    approval_method = "interactive"
                    break
                elif answer in ("r", "revise", "revise request"):
                    revised, _ = edit_request(path, context["request"], args)
                    if not revised:
                        print("Empty revised request; update cancelled.")
                        return 0
                    context = engine.build_context(container, index, revised, container_path=str(path),
                                                   fingerprint=fingerprint, evidence=args.evidence,
                                                   base_prompt=read_text(args.base_prompt), standing_brief=read_text(args.brief), with_facts=args.with_facts,
                                                   as_of=args.as_of.isoformat() if args.as_of else None)
                    break
                elif answer in ("c", "cancel"):
                    print("Update cancelled; saved plan retained.")
                    return 0
                else:
                    print("Choose an action explicitly; Enter does not approve.")
            if answer in ("a", "approve"):
                break
    engine.validate_freshness(artifact, path)
    approval = {"method": approval_method, "at": datetime.now(timezone.utc).isoformat(),
                "plan_id": artifact["id"], "plan_digest": artifact["digest"]}
    if attempt:
        if artifact["plan"].get("questions") or not artifact["plan"].get("changes"):
            raise ValueError("Recovery requires an actionable plan with no unresolved questions")
        raw = attempt["raw_data"]
        raw["recovery_path"] = str(artifact_path)
        report = engine.prepare_report(attempt["body"], artifact, raw)
    else:
        report, raw = engine.generate(artifact, approved=True, use_cache=not args.no_cache,
                                      quiet=args.quiet, verbose=args.verbose, recovery_dir=Path(artifact_path).parent)
    try:
        updated, index = revisions.commit_update(path, artifact["context"]["fingerprint"],
                                                 artifact["context"]["parent_index"], report, raw, artifact, approval)
    except (ValueError, OSError) as error:
        raise ValueError(f"{error} Generated response retained at {raw.get('recovery_path', artifact_path)}. "
                         "Use --recover-attempt with that artifact after resolving the failure; "
                         "changed inputs require fresh review.") from error
    print(f"Saved {revisions.version_label(updated['story'][index])}; report index {index + 1}; not fact-checked.")
    return run_checks(path, index, args) if args.check else 0


def main(argv=None):
    parser = parser_for_cli()
    args = parser.parse_args(argv)
    validate_options(parser, args, sys.stdin.isatty())
    require_config()
    load_cross_env()
    try:
        return run(args)
    except (KeyboardInterrupt, EOFError):
        print("\nUpdate cancelled; saved drafts/plans are retained.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"st-update: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
