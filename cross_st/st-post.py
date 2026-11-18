#!/usr/bin/env python3
"""
st-post — Post a report to Discourse

```
st-post subject.json                         # post to Test (cleared daily) — safe default
st-post --category private subject.json      # post to your private category
st-post --category reports subject.json      # post to your public portfolio
st-post --category prompt-lab --prompt subject.json  # post the prompt to 🧪 Prompt Lab
st-post -s 2 subject.json                          # post report 2
st-post --site MySite subject.json          # post to a named Discourse site
st-post --check                             # verify credentials without posting
```

Options: -s story  --site  --category  --fact  --prompt  --check  -v  -q
"""
import argparse
import json
import os
import sys
from mmd_startup import load_cross_env, require_config

from discourse import (
    get_discourse_slugs_sites,
    get_discourse_site,
    resolve_category,
)
from mmd_process_report import add_mp3_player, add_mp3_player_top, sanitize_at_mentions
from _report_store import load_snapshot, authored_prompt, StoreError
from _report_content import (content_identity, published_title_exists, save_publication, archive_publication)
from pathlib import Path
from discourse import MmdDiscourseClient


def main():
    require_config()
    load_cross_env()

    # Help must be available before Discourse setup.
    help_requested = any(flag in sys.argv[1:] for flag in ("-h", "--help"))
    slugs, sites = ([], []) if help_requested else get_discourse_slugs_sites()
    default_site = slugs[0] if slugs else None

    parser = argparse.ArgumentParser(
        prog='st-post',
        description=("Post a report to social media."
                      " At minimum include the report .json file."
                      " The title and body can be tailored by editing the .md and .title files."
                      " The  json can be overridden by .title and .md files.")
    )
    parser.add_argument('files', nargs='*',
                        help="Files of to process")
    parser.add_argument('--site', type=str, choices=slugs or None, default=default_site,
                        help=f"Select Discourse site to use, default is {default_site}")
    # When -s is specified, an integer must follow; if not, argparse will raise an error.
    parser.add_argument('-s', '--story', type=int, default=1,
                        help='Select report to publish: default 1')
    parser.add_argument('-f', '--fact', type=int,
                        help='Reply with fact-check to the post, default: no reply')
    parser.add_argument('--category', type=str, default='test',
                        help=('Where to post. Accepts: '
                              '"private" (your private area), '
                              'a numeric Discourse category ID, or '
                              '— on crossai.dev only — "test" (id=6, sandbox '
                              'cleared daily), "reports" (id=16, public '
                              'portfolio), "prompt-lab" (id=17). '
                              'Default: "test".'))
    parser.add_argument('--check', action='store_true',
                        help='Validate Discourse credentials and connection without posting')
    parser.add_argument('--prompt', action='store_true',
                        help='Post the prompt text from the container instead of the report (useful with --category prompt-lab)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output, default: verbose off')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Enable minimal output')
    args = parser.parse_args()


    # ── --check: validate credentials without posting ─────────────────────────
    if args.check:
        import requests as _req
        print(f"Checking Discourse site: {args.site}")
        site = get_discourse_site(args.site, sites)
        key = site.get("api_key", "")
        username = site.get("username", "")
        url = site.get("url", "").rstrip("/")
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else "****"
        print(f"  URL      : {url}")
        print(f"  Username : {username}")
        print(f"  API key  : {masked}  (len={len(key)})")
        print(f"  Category : {site.get('category_id')}")
        print()

        # Raw requests call — bypasses pydiscourse entirely
        # This isolates whether the problem is in the library or the credentials
        test_url = f"{url}/session/current.json"
        print(f"  Testing: GET {test_url}")
        try:
            resp = _req.get(
                test_url,
                headers={
                    "Api-Key": key,
                    "Api-Username": username,
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            print(f"  HTTP status : {resp.status_code}")
            if resp.status_code == 200:
                data = resp.json()
                cuser = data.get("current_user", {})
                print(f"  Auth        : ✓  logged in as {cuser.get('username', '?')}")
                print(f"  Trust level : {cuser.get('trust_level', '?')}")
                print(f"  Admin       : {cuser.get('admin', False)}")
            elif resp.status_code == 403:
                print(f"  Auth        : ✗  403 Forbidden — key is valid JSON but rejected")
                print(f"  Response    : {resp.text[:300]}")
                print()
                print("  Diagnosis:")
                print("    The API key exists but is being rejected. Check:")
                print("    1. Admin panel → API → key must have 'All Users' or your username scope")
                print("    2. The key owner username must exactly match the 'username' field")
                print("    3. Try: Admin → Users → your_user → Permissions → 'allow api access'")
            elif resp.status_code == 404:
                print(f"  Auth        : ✗  404 — URL may be wrong: {url}")
            else:
                print(f"  Auth        : ✗  HTTP {resp.status_code}")
                print(f"  Response    : {resp.text[:300]}")
        except Exception as e:
            print(f"  Connection  : ✗  {e}")
            print("  Check the URL is reachable and correct")

        # ── Test upload endpoint ──────────────────────────────────────────────
        print()
        print(f"  Testing upload endpoint: POST {url}/uploads.json")
        import io as _io
        try:
            # Minimal valid MP3 header — just enough to test the endpoint
            # without uploading a real file
            tiny_mp3 = bytes([
                0xFF, 0xFB, 0x90, 0x00,   # MP3 frame sync + header
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
                0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            ])
            upload_resp = _req.post(
                f"{url}/uploads.json",
                headers={
                    "Api-Key": key,
                    "Api-Username": username,
                },
                files={"file": ("test.mp3", _io.BytesIO(tiny_mp3), "audio/mpeg")},
                data={"type": "composer", "synchronous": "true"},
                timeout=15,
            )
            print(f"  HTTP status : {upload_resp.status_code}")
            print(f"  Response    : {upload_resp.text[:400]}")
            if upload_resp.status_code == 200:
                print(f"  Upload      : ✓  endpoint accepts uploads")
            elif upload_resp.status_code == 422:
                print()
                print("  Upload      : ✗  422 Unprocessable — file rejected (expected for")
                print("                   a tiny test file — but auth is working)")
            elif upload_resp.status_code == 403:
                print()
                print("  Upload      : ✗  403 on uploads.json specifically")
                print("  This Discourse instance may have uploads restricted.")
                print("  Check: Admin → Settings → Files → 'authorized extensions'")
                print("         and ensure 'mp3' is listed.")
                print("  Also check: Admin → Settings → Files → 'allow staff to upload any file type'")
        except Exception as e:
            print(f"  Upload      : ✗  {e}")
        sys.exit(0)

    # get the site json structure based on user preference
    site = get_discourse_site(args.site, sites)

    # Resolve the posting category for the story post.
    # Accepts: "private", a numeric ID, or (on crossai.dev only) the
    # named shortcuts "test" / "reports" / "prompt-lab". See
    # discourse.resolve_category() for the full rules.
    try:
        post_category_id = resolve_category(site, args.category)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(2)

    file_list = args.files
    if len(file_list) == 0:
        print("Enter at least one file to post.")
        sys.exit(1)

    # Dictionary to hold files by type
    files_by_type = {
        'jpg': [],  # Story image attachment
        'json': [],  # Story container
        'md': [],  # Story markdown content
        'mp3': [],  # Story audio attachment
        'mp4': [],  # Story video attachment
        'png': [],  # Story image attachment
        'title': [],  # Story title
        'txt': [],  # Story text content
    }

    # Classify files by their extension
    for file in file_list:
        _, ext = os.path.splitext(file)
        ext = ext.lstrip('.').lower()  # Remove leading dot and make lowercase
        if ext in files_by_type:
            files_by_type[ext].append(file)
        else:
            print(f"Warning: Unrecognized file extension '{ext}' for file {file}")

    fact_report = ""
    file_json = ""
    file_prefix = ""
    story_markdown = ""
    story_title = ""
    topic_id = None

    # Load content from json container first, override with specific content
    if len(files_by_type['json']) > 0:
        file_json = files_by_type['json'][0]
        try:
            main_container, _ = load_snapshot(file_json)

            if args.prompt:
                if not main_container.get("story") and args.story == 1:
                    data = main_container.get("data", [])
                    prompt_text = data[0].get("prompt") if data else None
                else:
                    if not 1 <= args.story <= len(main_container.get("story", [])):
                        raise ValueError("Report index is out of range.")
                    prompt_text = authored_prompt(main_container, args.story - 1)
                if not prompt_text:
                    print("Error: No prompt found in container.")
                    sys.exit(1)
                file_prefix = Path(file_json).stem
                story_title = f"Prompt: {file_prefix}"
                story_markdown = f"```\n{prompt_text.strip()}\n```"
            else:
                # Confirm story parameter, get story
                length = len(main_container.get("story", []))
                if 1 <= args.story <= length:
                    select_story = main_container["story"][args.story-1]
                    selected_identity = content_identity(select_story)
                else:
                    if not args.quiet:
                        print(f"Report item out of range: {args.story}")
                    sys.exit(1)

                # Confirm fact parameter, get fact report
                if args.fact is not None:
                    length = len(select_story.get("fact", []))
                    if 1 <= args.fact <= length:  # Validate range
                        fact_obj = select_story["fact"][args.fact-1]
                        fact_report = fact_obj.get("report")
                    else:
                        print(f"Fact item out of range {args.fact}")
                        sys.exit(1)

            if args.verbose:
                print(f"Report container json successfully read.")

            if not args.prompt:
                file_prefix = Path(file_json).stem  # filename no extension
                story_markdown = select_story.get("markdown") or select_story.get("text", "")
                # story_text = post_story['text']  # Currently on MD is used
                story_title = select_story['title']
                topic_id = select_story.get('topic_id')

        except FileNotFoundError:
            print(f"Error: The file {file_json} does not exist.")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Error: The file {file_json} contains invalid JSON.")
            sys.exit(1)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            sys.exit(1)

    # If there is a title file, override title from story container
    if len(files_by_type['title']) > 0:
        with open(files_by_type['title'][0], 'r') as file:
            story_title = file.read()

    # If there is a md file, override story from story container
    if len(files_by_type['md']) > 0:
        with open(files_by_type['md'][0], 'r') as file:
            story_markdown = file.read()

    # Remote copies are independent; never overwrite a previous post implicitly.
    base_url = site["url"]
    if file_json and args.fact is None:
        for report in main_container.get("story", []):
            archive_publication(main_container, report)
        if published_title_exists(main_container, base_url, story_title):
            print("Error: This title has already been posted to this site. Choose a new title to publish another post.")
            sys.exit(1)
    if not story_title.strip() or not story_markdown.strip():
        print("Error: A non-empty title and report body are required.")
        sys.exit(1)

    if args.fact is not None and file_json and select_story.get("post_url"):
        from urllib.parse import urlsplit
        published_site = urlsplit(select_story["post_url"])
        selected_site = urlsplit(base_url)
        if (published_site.scheme, published_site.netloc) != (selected_site.scheme, selected_site.netloc):
            print("Error: The selected report was posted to a different site. Select that site to reply.")
            sys.exit(1)

    # Initialize the client
    client = MmdDiscourseClient(
        base_url,
        api_username=site["username"],
        api_key=site["api_key"],
    )
    # If there is a mp3 file, upload it to discourse and keep the url.
    # The url will be referenced in the post
    file_mp3 = files_by_type['mp3'][0] if files_by_type['mp3'] else ""
    mp3_url = ""
    post_url = ""

    if file_mp3:
        # Audio exports are independent copies. Only use the explicitly named file.
        if not os.path.isfile(file_mp3):
            print(f"Error: Audio file {file_mp3} does not exist. Generate it with st-speak first.")
            sys.exit(1)
        try:
            if not args.quiet:
                print(f"Uploading audio file: {file_mp3}")
            upload_resp = client.upload_file(file_mp3)
            mp3_url = upload_resp["url"]
        except Exception as exc:
            print(f"An upload error occurred: {exc}")
            sys.exit(1)

    if args.fact is not None:
        if mp3_url:
            fact_report = add_mp3_player_top(fact_report, file_mp3, mp3_url)
    else:
        if mp3_url:
            story_markdown = add_mp3_player(story_markdown, file_mp3, mp3_url)

    if args.fact is None:  # If not a fact-check post, it must be a regular post
        # Create the post
        try:
            print(f"Uploading post to {args.site}")
            post_response = client.create_post(
                sanitize_at_mentions(story_markdown),
                post_category_id,
                title=story_title,
            )
            topic_id = post_response['topic_id']
            topic_slug = post_response['topic_slug']
            post_url = f"{base_url}/t/{topic_slug}/{topic_id}"
            if not args.quiet:
                print(f"Post uploaded: {post_url}")
        except Exception as e:
            print(f"An error occurred: {e}")
            sys.exit(1)

        # Persist remote success without overwriting concurrent report/check changes.
        if file_json:
            receipt = {"site_url": base_url.rstrip("/"), "title": story_title,
                       "topic_id": topic_id, "post_url": post_url, "mp3_url": mp3_url,
                       "content_identity": selected_identity if not args.prompt else None}
            try:
                attached, recovery = save_publication(
                    file_json, args.story - 1,
                    selected_identity if not args.prompt else None, receipt)
            except StoreError as exc:
                print(str(exc))
                return
            if recovery:
                print(f"Post succeeded; local container could not be updated. Receipt: {recovery}")
            elif not attached and not args.prompt:
                print("Post succeeded; the local report changed meanwhile. Publication receipt saved separately in the container.")
    else:
        # Not a post but a fact-check reply
        # A story is given a topic_id after it is posted
        if topic_id is not None and fact_report != "":
            # Create the reply
            try:
                print(f"Uploading reply, length: {len(fact_report)}")
                post_response = client.create_post(
                    sanitize_at_mentions(fact_report),
                    post_category_id,
                    topic_id=topic_id,
                )
                response_topic_id = post_response['topic_id']
                print(f"Post uploaded, topic_id: {response_topic_id}")
            except Exception as e:
                print(f"An error occurred: {e}")
                sys.exit(1)
        else:
            if topic_id is None:
                print("Error: Report has not been posted yet — run st-post without -f first to create the topic.")
            else:
                print("Error: Fact check not complete — no fact report found for the selected report/fact index.")
            sys.exit(1)


if __name__ == "__main__":
    main()
