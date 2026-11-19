#!/usr/bin/env python3
"""
st-update — Update a selected report, then review the saved result

Source and output are explicit: -s N selects an existing SOURCE report.
It is required when the container has multiple reports. With only one report,
that report is selected automatically. A normal update appends a new output;
Cross assigns and prints its index.

By default, updates use the source report's saved provider and model, even if
that agent's configured model has since changed. Use --agent NAME to deliberately
choose a different author and its configured model. Imported content without an
AI author uses the configured default agent.

--iterate N reopens the update request associated with existing OUTPUT N and
replaces that output and its raw generation record. Source and output may be
the same report. Old entries remain untouched until both replacements are ready
and saved together. Successful iteration discards the previous output and raw
response; omit --iterate to keep them and append instead.

On the first update, --iterate is ignored with a message. Every supplied index
must still exist. It never specifies a future output number.

## Workflow

1. Run st-ls report.json to inspect report indices.
2. Run st-update -s 1 report.json and describe the changes in your editor.
3. Cross generates and saves the updated report, then prints its index and summary.
4. Inspect the saved report with st-edit --view-only --markdown -s 2 report.json.
5. Edit, iterate, append, print, post, or remove using that explicit index.

Review happens after saving. There is no plan-approval step, active-report state,
version footer, automatic browsing, fact-checking, or publishing. Inputs are the
saved source (including manual edits), useful authored intent, your request,
and any supplied evidence. Quiet mode retains the result and change summary.

## Examples

    st-update report.json                      # only one report exists; append
    st-update -s 1 --iterate 2 report.json       # source 1; replace output 2
    st-update -s 2 --iterate 2 report.json       # use edited output as its own source
    st-update -s 2 report.json                  # append from source 2
    st-update -s 1 --prompt changes.prompt --evidence notes.md --update-details report.json
    st-update -s 2 --show-summary --update-details report.json  # saved summary, no AI

Example request: "Add the supplied cost figures and revise the recommendation.
Keep my table, headings, and closing note. Identify any remaining uncertainty."
Deleting with st-rm -s N removes the associated pair and shifts later indices;
use st-ls again afterward. Local changes do not update a published Discourse post.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

from mmd_startup import require_config, load_cross_env
from cli_agent import add_agent_arg
import _report_store as store
import _report_update as engine


def parser_for_cli():
    overview, examples = __doc__.split('## Examples', 1)
    parser = argparse.ArgumentParser(prog='st-update', description=overview.strip(),
                                    epilog='Examples' + examples,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('json_file', type=Path, metavar='FILE.json', help='Existing report container')
    parser.add_argument('-s', '--story', dest='source', type=int, metavar='N',
                        help='Existing source index; required with multiple reports (display index with --show-summary)')
    parser.add_argument('--iterate', type=int, metavar='N', help='Existing output to regenerate; never a future index')
    parser.add_argument('--prompt', type=Path, metavar='FILE', help='Read update instructions from a UTF-8 file instead of the editor')
    parser.add_argument('--evidence', type=Path, metavar='FILE', action='append', default=[], help='Supplied UTF-8 evidence; repeatable')
    add_agent_arg(parser, help='Override the source author with this agent and its configured model; default: source provider/model')
    views = parser.add_mutually_exclusive_group()
    views.add_argument('--update-summary', action='store_true', help='Concise generated-change summary (default)')
    views.add_argument('--update-details', action='store_true', help='Detailed change notes and exact Markdown diff')
    parser.add_argument('--show-summary', action='store_true', help='Read the selected output\'s saved summary without generation or editing')
    parser.add_argument('--no-cache', action='store_true', help='Bypass AI cache; does not fetch new evidence')
    parser.add_argument('--no-spell', action='store_true', help='Skip optional Aspell when using the editor')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress, retaining result and summary')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show additional diagnostics')
    return parser


def select_source(container, explicit):
    reports = container.get('story', [])
    if explicit is None:
        if len(reports) != 1:
            raise ValueError('Multiple reports require an explicit source: use -s N (inspect indices with st-ls).'
                             if reports else 'No report is available to update.')
        return 0
    if explicit < 1 or explicit > len(reports):
        raise ValueError(f'Source report {explicit} does not exist. Use st-ls to inspect existing indices.')
    return explicit - 1


def edit_request(path, initial, args):
    fd, filename = tempfile.mkstemp(prefix=path.stem + '-update-', suffix='.prompt', dir=path.parent)
    draft = Path(filename)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        output.write(initial)
    try:
        editor = shlex.split(os.getenv('EDITOR') or 'vi')
        result = subprocess.run(editor + [str(draft)], check=False)
        if result.returncode:
            raise ValueError(f'Editor exited with status {result.returncode}; nothing saved. Request retained: {draft}')
        if not args.no_spell:
            aspell = shutil.which('aspell')
            if aspell:
                result = subprocess.run([aspell, 'check', str(draft)], check=False)
                if result.returncode:
                    raise ValueError(f'Spell check cancelled; nothing saved. Request retained: {draft}')
            elif not args.quiet:
                print("Spell check skipped: 'aspell' is not installed. Use --no-spell to disable this check.")
        return draft.read_text(encoding='utf-8'), draft
    except (OSError, KeyboardInterrupt):
        print(f'Request retained: {draft}', file=sys.stderr)
        raise


def run(args):
    if args.show_summary and (args.iterate is not None or args.prompt or args.evidence or args.agent or args.no_cache or args.no_spell):
        raise ValueError('--show-summary cannot be combined with update inputs, --iterate, --agent, --no-cache, or --no-spell.')
    path = args.json_file
    container, fingerprint = store.load_snapshot(path)
    source = select_source(container, args.source)
    if args.show_summary:
        pos = store.raw_index(container, source, required=True)
        summary = container['data'][pos].get('update_summary')
        if not summary:
            raise ValueError('No saved update summary exists for this report.')
        if engine.digest(container['story'][source].get('markdown', '')) != summary.get('output_sha256'):
            print('Note: this report has been edited since generation; this summary describes the generated output.')
        print(engine.render_summary(summary, details=args.update_details))
        return 0
    target = None
    if args.iterate is not None:
        if args.iterate < 1 or args.iterate > len(container['story']):
            raise ValueError(f'Iteration output {args.iterate} does not exist. --iterate requires an existing output index.')
        if not store.has_updates(container):
            print('Ignoring --iterate: no previous st-update output exists in this container.')
        else:
            target = args.iterate - 1
            store.raw_index(container, target, required=True)
            if not store.update_request(container, target):
                raise ValueError(f'Report {args.iterate} has no iterative update prompt. Omit --iterate to append a new output.')
    if not args.prompt and not sys.stdin.isatty():
        raise ValueError('Non-interactive updates require --prompt FILE with the update instructions.')
    from ai_handler import get_default_ai, check_api_key
    inherited = False
    if args.agent:
        spec = engine.identity(args.agent)
    else:
        spec = engine.source_identity(container, source)
        inherited = spec is not None
        if spec is None:
            spec = engine.identity(get_default_ai())
    agent = spec['agent']
    if not check_api_key(agent):
        raise ValueError(f'No usable credentials for agent {agent}; configure it with st-admin.')
    if not args.quiet:
        selection = ('Source report author' if inherited else
                     'Selected agent' if args.agent else 'Default agent for imported content')
        print(f"  {selection}: {agent} ({spec['provider']} / {spec['model']})", flush=True)
    draft = None
    if args.prompt:
        request = args.prompt.read_text(encoding='utf-8')
    else:
        initial = store.update_request(container, target) if target is not None else ''
        request, draft = edit_request(path, initial, args)
    request = request.strip()
    if not request:
        print('Empty update request; no update made.')
        if draft:
            draft.unlink(missing_ok=True)
        return 0
    try:
        inputs = engine.context_for(container, source, request, args.evidence)
        # Detect edits made during request editing before paying for generation.
        if store.load_snapshot(path)[1] != fingerprint:
            raise ValueError('Container changed while editing; reload it before updating.')
        raw, report, summary = engine.generate(inputs, container['story'][source], agent,
                                               model=spec['model'], use_cache=not args.no_cache,
                                               quiet=args.quiet, verbose=args.verbose)
        updated, index = store.commit_update(path, fingerprint, source, raw, report, request,
                                             summary=summary, target_index=target)
    except (Exception, KeyboardInterrupt):
        if draft:
            print(f'Request retained: {draft}', file=sys.stderr)
        raise
    if draft:
        try:
            draft.unlink(missing_ok=True)
        except OSError:
            print(f'Update saved; could not remove request draft: {draft}', file=sys.stderr)
    action = 'Replaced' if target is not None else 'Saved'
    print(f'{action} report {index + 1} in {path}; source report {source + 1}; not fact-checked.')
    print(engine.render_summary(summary, details=args.update_details))
    quoted = shlex.quote(str(path))
    print(f'View: st-edit --view-only --markdown -s {index + 1} {quoted}')
    print(f'Saved summary: st-update -s {index + 1} --show-summary {quoted}')
    return 0


def main():
    parser = parser_for_cli()
    args = parser.parse_args()
    require_config()
    load_cross_env()
    try:
        return run(args)
    except (EOFError, KeyboardInterrupt):
        print('Update cancelled; no incomplete output was saved.', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
