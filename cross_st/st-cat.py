#!/usr/bin/env python3
"""
## st-cat — Print report container fields to stdout

Reads a single report (or fact-check) from a .json container and prints the
requested field(s) to standard output.  Useful for piping report text into
other tools or shell scripts.

```
st-cat subject.json                 # print the prompt (default)
st-cat -t subject.json              # print title of report 1
st-cat --markdown -s 3 subject.json # print markdown of report 3
st-cat -f 2 -s 1 subject.json       # print fact-check report 2 from report 1
st-cat --text -s 2 subject.json     # print plain text body of report 2
st-cat --prompt subject.json        # print the selected report’s authored prompt
```

Options: -s report  -f fact  --title  --text  --markdown  --hashtags  --spoken  --prompt
"""

import argparse
import json
import os
import sys
from mmd_startup import require_config


def main():
    require_config()
    parser = argparse.ArgumentParser(
        prog='st-cat',
        description="Read elements of a .json container and print to standard out.")
    parser.add_argument('json_file', type=str,
                        help='Path to the JSON file', metavar='file.json')
    parser.add_argument('-s', '--story', type=int, default=1,
                        help='Report number (integer), default: 1')
    parser.add_argument('-f', '--fact', type=int,
                        help='Fact-check report number (integer), default: none')
    parser.add_argument('--markdown', action='store_true',
                        help='Report markdown, default: off')
    parser.add_argument('--hashtags', action='store_true',
                        help='Report hashtags, default: off')
    parser.add_argument('--spoken', action='store_true',
                        help='Report spoken text, default: off')
    parser.add_argument('--text', action='store_true',
                        help='Report text body, default: off')
    parser.add_argument('-t', '--title', action='store_true',
                        help='Report title, default: off')
    parser.add_argument('--prompt', action='store_true',
                        help='Print the selected report’s authored prompt (default if no other field specified)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output, default: off')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Enable minimal output')
    args = parser.parse_args()

    # Default to --prompt if no output field was requested
    output_requested = any([
        args.title, args.text, args.markdown,
        args.hashtags, args.spoken, args.fact is not None,
        args.prompt,
    ])
    if not output_requested:
        args.prompt = True

    file_prefix = args.json_file.rsplit('.', 1)[0]  # Split from the right, only once
    file_json = file_prefix + ".json"

    try:
        if not os.path.isfile(file_json):
            print(f"Error: The file {args.json_file} does not exist.")
            sys.exit(1)

        with open(file_json, 'r') as file:
            main_container = json.load(file)

    except json.JSONDecodeError:
        print(f"Error: The file {file_json} contains invalid JSON.")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

    if args.verbose:
        print(f"Loaded: {file_json}", file=sys.stderr)

    # Resolve the selected report’s authored request, including updated reports.
    if args.prompt:
        prompt_text = ""
        data = main_container.get("data", [])
        reports = main_container.get("story", [])
        if reports:
            if not 1 <= args.story <= len(reports):
                print(f"Report item out of range: {args.story}", file=sys.stderr)
                sys.exit(1)
            from _report_store import authored_prompt, StoreError
            try:
                prompt_text = authored_prompt(main_container, args.story - 1) or ""
            except StoreError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                sys.exit(1)
        elif data and args.story == 1:
            prompt_text = data[0].get("prompt", "")
        if prompt_text:
            print(prompt_text)
        else:
            if not args.quiet:
                print("No prompt found in container.")
            sys.exit(1)
        # If --prompt is the only flag, we can stop here
        if not any([args.title, args.text, args.markdown,
                    args.hashtags, args.spoken, args.fact is not None]):
            return

    # Confirm story parameter, get story
    length = len(main_container.get("story", []))
    if 1 <= args.story <= length:
        select_story = main_container["story"][args.story - 1]
    else:
        if not args.quiet:
            print(f"Report item out of range: {args.story}")
        sys.exit(1)

    if args.title:
        print(select_story.get("title"))

    if args.text:
        print(select_story.get("text"))

    if args.spoken:
        print(select_story.get("spoken"))

    if args.markdown:
        print(select_story.get("markdown"))

    if args.hashtags:
        print(select_story.get("hashtags"))

    if args.fact is not None:
        length = len(select_story.get("fact", []))
        if 1 <= args.fact <= length:
            fact_obj = select_story["fact"][args.fact - 1]
            fact_report = fact_obj.get("report")
            print(fact_report)
        else:
            if not args.quiet:
                print(f"Fact item out of range: {args.fact}")
            sys.exit(1)


if __name__ == "__main__":
    main()
