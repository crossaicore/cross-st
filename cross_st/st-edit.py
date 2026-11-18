#!/usr/bin/env python3
"""
st-edit — Edit or view report fields in a container

```
st-edit subject.json                    # edit active report in $EDITOR
st-edit -s 2 subject.json              # edit report 2
st-edit --markdown subject.json        # edit the Markdown body
st-edit --view-only subject.json       # view without editing
```

Options: -s report  --markdown  --text  --title  --spoken  --view  --view-only  -v  -q
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import subprocess
from _report_revisions import (RevisionError, is_revisioned, load_snapshot, selected_indices,
    render_report, report_body, commit_manual, atomic_write, content_digest)
from mmd_startup import load_cross_env, require_config



def _manual_report(parent, field, updated):
    """Rebuild derived fields from the chosen source without carrying stale checks."""
    from mmd_process_report import remove_markdown, get_hashtags, clean_newlines_preserve_paragraphs
    from mmd_for_speaking import for_speaking
    body = report_body(parent)
    if field in ("markdown", "text"):
        body = updated
    plain = clean_newlines_preserve_paragraphs(remove_markdown(body))
    return {"make": parent.get("make", "human"), "model": parent.get("model", ""),
            "title": updated if field == "title" else parent.get("title", ""),
            "markdown": body, "text": plain,
            "spoken": updated if field == "spoken" else for_speaking(plain, False),
            "hashtags": get_hashtags(body), "role": "author", "edited_by": "human",
            "attribution": parent.get("attribution", ""), "fact": []}


def _save_edit(path, container, fingerprint, report_index, field, updated, fact_index=None):
    """Persist an edit with CAS; report edits create successors once tracking exists."""
    report = container["story"][report_index]
    if not updated.strip():
        raise RevisionError("Empty edited content; nothing saved.")
    if fact_index is not None:
        fact = report["fact"][fact_index]
        fact["report"] = updated
        if is_revisioned(container):
            fact.update(report_id=report["report_id"], content_sha256=content_digest(report), manually_edited=True)
        atomic_write(path, container, fingerprint)
        return container, report_index
    if is_revisioned(container):
        return commit_manual(path, fingerprint, report_index, _manual_report(report, field, updated), field)
    report[field] = updated
    atomic_write(path, container, fingerprint)
    return container, report_index


def main():
    require_config()
    load_cross_env()
    parser = argparse.ArgumentParser(
        prog='st-edit',
        description='Edit or view report fields. Tracked report edits create a new revision.'
                    '\nRun st-gen first.')

    # A json file is required
    parser.add_argument('json_file', type=str,
                        help='Path to the JSON file', metavar='file.json')
    # Data selection is optional, default select data 1
    parser.add_argument('-s', '--story', type=int, default=None,
                        help='Report index; default active report, or report 1 for legacy containers')
    parser.add_argument('-f', '--fact', type=int,
                        help='Fact-check to edit (integer), default None')
    parser.add_argument('-spoken', '--spoken', action='store_true',
                        help='Edit the text to speech source text default: do not edit')
    parser.add_argument('-md', '--markdown', action='store_true',
                        help='Edit the markdown data, default: do not edit')
    parser.add_argument('-title', '--title', action='store_true',
                        help='Edit the title data, default: do not edit')
    parser.add_argument('-text', '--text', action='store_true',
                        help='Edit the text data, default: do not edit')
    parser.add_argument('--view', action='store_true',
                        help='View with Glow and edit with Vi, default: off')
    parser.add_argument('--view-only', action='store_true',
                        help='View with Glow, default: off')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Minimal output, default: quiet on')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output, default: verbose off')

    args = parser.parse_args()
    file_prefix = args.json_file.rsplit('.', 1)[0]  # Split from the right, only once
    file_json = file_prefix + ".json"

    edit_list = []
    if args.title:
        edit_list.append("title")
    if args.markdown:
        edit_list.append("markdown")
    if args.text:
        edit_list.append("text")
    if args.spoken:
        edit_list.append("spoken")
    if args.fact is not None:
        edit_list.append("fact")
    if len(edit_list) == 0:
        edit_list.append("markdown")
    if len(edit_list) != 1:
        print(f"Only one edit at a time please: {edit_list}")
        sys.exit(0)

    try:
        if not os.path.isfile(file_json):
            print(f"Error: The file {args.json_file} does not exist.")
            sys.exit(1)

        main_container, file_fingerprint = load_snapshot(file_json)

        if args.verbose:
            print(f"Story container {file_json} successfully read.")

    except json.JSONDecodeError:
        print(f"Error: The file {file_json} contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    try:
        candidates = selected_indices(main_container, args.story)
        if not candidates:
            raise RevisionError("Container has no reports.")
        if is_revisioned(main_container) and len(candidates) != 1:
            raise RevisionError("Several active reports; select one with -s N.")
        story_index = candidates[0]
        args.story = story_index + 1
    except RevisionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    stories = main_container.get("story", [])
    if not stories or story_index >= len(stories) or story_index < 0:
        print(f"No such story: {story_index + 1}")
        sys.exit(1)

    story = stories[story_index]
    ai_tag = f"{story.get('make')}:{story.get('model')}"

    """
    For item to edit
    1. Get the text to edit from the story container
    2. Write the text to a file
    3. Spawn a task for the user the edit the file
    4. When control returns, read the file
    5. Save the data back to the container
    When done with all items, write the container back to disk, exit
    """

    item = edit_list[0]
    text_to_edit = ""
    fact_obj = None
    if args.fact is not None:  # Fact is two-level case, all others are a member of story
        length = len(story.get("fact", []))
        if 1 <= args.fact <= length:  # Validate range
            fact_obj = story["fact"][args.fact - 1]
            text_to_edit = fact_obj.get("report")
        else:
            print(f"Fact item out of range {args.fact}")
            sys.exit(1)
    else:
        text_to_edit = story.get(item, "")
        if is_revisioned(main_container) and item == "markdown":
            text_to_edit = report_body(story)
        if args.view_only and item in ("markdown", "text"):
            text_to_edit = render_report(story, item)

    # Record the hash, to determine if any mods are made and disk write is necessary
    md5_hash = hashlib.md5(text_to_edit.strip().encode('utf-8')).hexdigest()

    # Create a temporary file that persists after closing
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
        temp_file.write(text_to_edit)
        temp_file.flush()  # Ensure content is written to disk
        temp_path = temp_file.name  # Get the file path

    fact_select = ""
    if item=="fact":
        fact_select = f":{args.fact}"  # When item="fact", title "fact:n"
    editor_was_active = False

    # Resolve grip binary — auto-install on first use if not present
    import shutil as _shutil
    import subprocess as _sp_grip
    _grip_bin = _shutil.which("grip") or os.path.join(os.path.dirname(sys.executable), "grip")
    if (args.view or args.view_only) and not os.path.isfile(_grip_bin):
        print("  grip not installed — installing now (one-time, ~2 MB)…", flush=True)
        _install = _sp_grip.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "grip"],
            capture_output=True, text=True
        )
        if _install.returncode != 0:
            print("Error: auto-install of grip failed.")
            print(_install.stderr[-400:].strip() if _install.stderr else "(no output)")
            sys.exit(1)
        _grip_bin = _shutil.which("grip") or os.path.join(os.path.dirname(sys.executable), "grip")
        print("  grip installed. ✓", flush=True)

    cmd = [
        _grip_bin, "--browser", "--quiet",
        f"--title={file_json} s:{args.story} {item}{fact_select} {ai_tag}",
        temp_path,
        "0",   # address "0" = OS assigns a free port — avoids conflicts on rapid re-use
    ]
    # Known grip startup noise — suppress these, surface anything else as warnings
    _GRIP_NOISE = {
        "* serving flask app",
        "* debug mode:",
        "* running on",
        "* restarting with",
        "* debugger is",
        "* debugger pin:",
        "use a production wsgi server instead",
        # grip dependency SyntaxWarnings under Python 3.13+ (docopt, path_and_address)
        "syntaxwarning",
        "invalid escape sequence",
        "did you mean",
        "a raw string is also an option",
        "docopt.py",
        "path_and_address",
        "validation.py",
        "warnings.warn",
        "site-packages",
        "name = re.findall",
        "value = re.findall",
        "matched = re.findall",
        "split = re.split",
        "_hostname_re = re.compile",
    }

    def _launch_grip(cmd, detach=False):
        """
        Start grip and return (process, port, error_lines).

        Uses a background thread to read stderr so we never block waiting for
        grip's pipe. Waits up to 3 s for grip to either bind a port or fail.

        If detach=True, grip is fully detached from this process (view_only mode):
        stdin/stdout/stderr are redirected to /dev/null, the process is in its
        own session, and st-edit exits without killing it.

        Returns (None, None, [error_msg]) on failure.
        """
        import re as _re
        import threading as _threading

        lines_seen = []
        port_found = [None]
        failed = [False]

        if detach:
            # Fully detached — grip outlives st-edit
            try:
                proc = subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,   # merge stdout+stderr → single stream
                )
            except FileNotFoundError:
                return None, None, ["grip binary not found after install — please report this bug."]
            except OSError as e:
                return None, None, [f"Failed to start grip: {e}"]
        else:
            try:
                proc = subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,   # merge stdout+stderr → single stream
                )
            except FileNotFoundError:
                return None, None, ["grip binary not found after install — please report this bug."]
            except OSError as e:
                return None, None, [f"Failed to start grip: {e}"]

        def _read_stderr():
            try:
                for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    lines_seen.append(line)
                    m = _re.search(r":(\d{4,5})", line)
                    if m:
                        port_found[0] = m.group(1)
                    if proc.poll() is not None and proc.returncode not in (None, 0):
                        failed[0] = True
            except Exception:
                pass

        t = _threading.Thread(target=_read_stderr, daemon=True)
        t.start()

        # Wait up to 3 s for grip to bind its port or exit with an error
        deadline = time.time() + 3
        while time.time() < deadline:
            if port_found[0] or failed[0]:
                break
            if proc.poll() is not None:
                # Process exited — give reader thread a moment to drain
                t.join(timeout=0.5)
                break
            time.sleep(0.05)

        # Check for startup failure
        if proc.poll() is not None and proc.returncode not in (None, 0):
            error_lines = [f"grip exited with code {proc.returncode}"]
            error_lines += [l for l in lines_seen
                            if l.strip() and not any(n in l.lower() for n in _GRIP_NOISE)]
            return None, None, error_lines

        # Surface any unexpected output as warnings
        warnings = [l for l in lines_seen
                    if l.strip() and not any(n in l.lower() for n in _GRIP_NOISE)]

        port = port_found[0] or "6419"
        return proc, port, warnings

    def _kill_stale_grip():
        """Terminate any grip processes left over from previous view-only calls."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "grip.*--browser"],
                capture_output=True, text=True
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    os.kill(int(pid_str), 15)  # SIGTERM
                except (ProcessLookupError, ValueError):
                    pass
        except Exception:
            pass  # pgrep unavailable or other OS issue — not fatal

    if args.view_only:
        # Kill any grip instances left from previous view calls before starting a new one
        _kill_stale_grip()

        # Detach grip fully — it must keep running after st-edit exits so the
        # browser can connect. --port=0 lets the OS assign a free port each time.
        # The temp file stays in /tmp and is cleaned up by the OS.
        grip_process, port, errors = _launch_grip(cmd, detach=True)

        if grip_process is None:
            print("  Error: could not launch grip browser preview.")
            for e in errors:
                print(f"    {e}")
            try:
                os.remove(temp_path)
            except OSError:
                pass
        else:
            if errors:
                print("  grip warning(s):")
                for e in errors:
                    print(f"    {e}")
            print(f"  Displayed on http://localhost:{port}")
            # Do NOT kill grip — it must keep serving until the browser loads.
            # Do NOT delete temp_path — grip is still reading it.

        sys.exit(0)

    if args.view:  # View and edit — grip runs alongside vi, killed when vi exits
        grip_process, port, errors = _launch_grip(cmd, detach=False)

        if grip_process is None:
            print("  Warning: grip browser preview unavailable.")
            for e in errors:
                print(f"    {e}")
            print("  Continuing with editor only.")
        else:
            if errors:
                print("  grip warning(s):")
                for e in errors:
                    print(f"    {e}")
            print(f"  Displayed on http://localhost:{port}")

        try:
            time.sleep(1)  # Brief pause so grip is ready before vi opens
            editor_was_active = True
            import shlex
            editor_result = subprocess.run(shlex.split(os.getenv("EDITOR", "vi")) + [temp_path])

        finally:
            if grip_process is not None:
                grip_process.terminate()
                grip_process.wait()
                grip_process.kill()
    else:  # Edit only
        editor_was_active = True
        import shlex
        editor_result = subprocess.run(shlex.split(os.getenv("EDITOR", "vi")) + [temp_path])

    if editor_was_active and editor_result.returncode != 0:
        print(f"Editor exited without saving to the container. Draft retained: {temp_path}", file=sys.stderr)
        sys.exit(1)

    if editor_was_active:
        # Editing is complete, read updated content
        with open(temp_path, "r") as temp_file:
            updated_content = temp_file.read()
        updated_content = updated_content.strip()  # vi adds unwanted \n


        # Test if the content changed
        updated_md5_hash = hashlib.md5(updated_content.encode('utf-8')).hexdigest()
        if updated_md5_hash != md5_hash:
            try:
                main_container, saved_index = _save_edit(
                    file_json, main_container, file_fingerprint, story_index, item,
                    updated_content, args.fact - 1 if args.fact is not None else None)
            except (ValueError, OSError) as exc:
                print(f"Error: {exc}\nEdited draft retained: {temp_path}", file=sys.stderr)
                sys.exit(1)
            os.remove(temp_path)

            if not args.quiet:
                print(f"Container updated: {file_json}")
        else:
            os.remove(temp_path)
            if not args.quiet:
                print(f"Container unchanged: {file_json}")


if __name__ == "__main__":
    main()
