"""
st-ask CLI: local FAQ-driven help for users with no API key.
"""
import sys
import os
import json
import argparse
from cross_st._ask_match import find_matches
from cross_st._ask_scrub import scrub
from cross_st import ai_handler
from cross_st import ai_error_handler
from cross_st import mmd_startup
from cross_st import _markdown


# ── Escape-hatch links (shown on every Full-LLM answer, per st-ask.md §1) ──
# NOTE: crossai.dev has no "help" category and GitHub Discussions is not enabled
# on this repo, so the community link points at the Discourse site root (always
# resolves). The wiki base resolves once the GitHub wiki is published.
_WIKI_BASE = "https://github.com/crossaicore/cross-st/wiki"
_DISCOURSE_URL = "https://crossai.dev"
_ISSUES_URL = "https://github.com/crossaicore/cross-st/issues"

_LLM_SEE_ALSO = (
    "\nSee also:\n"
    f"  • Wiki:      {_WIKI_BASE}\n"
    f"  • Community: {_DISCOURSE_URL}\n"
    f"  • Issues:    {_ISSUES_URL}"
)

# Labelled link lists for the escape-hatch blocks. In a rendering-capable
# terminal these become OSC 8 clickable hyperlinks (MDR-6); piped / --no-render
# output stays as plain bare-URL text for easy copy-paste.
_SEE_ALSO_LINKS = (
    ("Wiki", _WIKI_BASE),
    ("Community", _DISCOURSE_URL),
    ("Issues", _ISSUES_URL),
)
_NO_MATCH_LINKS = (
    ("Community", _DISCOURSE_URL),
    ("Issues", _ISSUES_URL),
)


def _print_link_block(header, links, render_pref=None):
    """Print a labelled link list.

    In a rendering-capable terminal each URL is shown in full **and** made an
    OSC 8 clickable hyperlink (the visible URL text is the clickable target),
    so users can both see and click/copy it. When rendering is off (piped,
    redirected, --no-render, NO_COLOR, CROSS_MARKDOWN=off) it prints plain
    bare-URL text.
    """
    if _markdown.should_render(sys.stdout, render_pref):
        lines = []
        if header:
            lines.append(f"**{header}**\n")
        for label, url in links:
            # Visible link text is the URL itself → the URL stays on screen and
            # is clickable. A distinct label (e.g. "Wiki") prefixes it.
            if label and label != url:
                lines.append(f"- {label}: [{url}]({url})")
            else:
                lines.append(f"- [{url}]({url})")
        print()
        _markdown.print_markdown("\n".join(lines), render=True)
    else:
        if header:
            print(f"\n{header}")
        for label, url in links:
            print(f"  • {label}: {url}")

# System-prompt rules for the Full-LLM tier (ASK-14). The corpus
# (support_content.md) is injected as the reference material.
_SYSTEM_RULES = (
    "You are st-ask, the built-in help assistant for the cross-st "
    "command-line tool.\n"
    "Answer the user's question using ONLY the reference material below.\n"
    "Rules:\n"
    "  1. Only reference flags, commands, and file paths that appear in the "
    "reference material. Never invent flags or behaviour.\n"
    "  2. If the reference does not cover the question, say so plainly and "
    "point the user to the wiki — do not guess.\n"
    "  3. Be concise and practical; prefer copy-pasteable commands.\n"
    "  4. Never ask the user to run cloud services or share secrets.\n"
    "  5. When you mention an st-* command, format it as a markdown link to its "
    "wiki page, e.g. [st-print](https://github.com/crossaicore/cross-st/wiki/st-print).\n"
    "  6. Do NOT add your own 'See also' section — st-ask appends one "
    "automatically. End with the answer itself.\n\n"
    "----- REFERENCE MATERIAL BEGINS -----\n"
    "{corpus}\n"
    "----- REFERENCE MATERIAL ENDS -----\n"
)

_FAQ = [
    {"id": "install", "question": "How do I install cross-st?", "answer": "Run: pipx install cross-st"},
    {"id": "upgrade", "question": "How do I upgrade cross-st?", "answer": "Run: st-admin --upgrade"},
    {"id": "api_key", "question": "How do I add an API key?", "answer": "Run: st-admin --setup and follow the prompts."},
    {"id": "help", "question": "Where can I get help?", "answer": "Ask the community at https://crossai.dev or file an issue at https://github.com/crossaicore/cross-st/issues"},
    {"id": "uninstall", "question": "How do I uninstall cross-st?", "answer": "Run: pipx uninstall cross-st"},
]

FOOTER = "(local lookup — for full answers add an AI key with 'st-admin --setup')"


def _has_api_key():
    # Minimal: check for any known API key env var
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        if os.getenv(k):
            return True
    return False

def _print_answer(entry, render_pref=None):
    _markdown.print_markdown(f"\n{entry['answer']}", render=render_pref)
    if entry.get('see_also'):
        _print_link_block("See also:", [("Documentation", entry['see_also'])], render_pref)
    _markdown.print_muted(f"\n{FOOTER}", render=render_pref)

def _print_no_match(render_pref=None):
    print("\nI don’t have a canned answer for that. Try:")
    _print_link_block(None, _NO_MATCH_LINKS, render_pref)
    print("\nStarter questions:")
    for entry in _FAQ[:5]:
        print(f"  - {entry['question']}")
    _markdown.print_muted(f"\n{FOOTER}", render=render_pref)

def _load_support_content():
    path = os.path.join(os.path.dirname(__file__), "data", "support_content.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception:
        return None

def _build_system_prompt():
    """Return the Full-LLM system prompt (rules + corpus), or None if the
    corpus is missing."""
    corpus = _load_support_content()
    if not corpus:
        return None
    return _SYSTEM_RULES.format(corpus=corpus)

def _select_agent(args):
    # Precedence per st-ask.md §2: --agent → ASK_AGENT → DEFAULT_AGENT
    if getattr(args, "agent", None):
        return args.agent
    if os.getenv("ASK_AGENT"):
        return os.getenv("ASK_AGENT")
    try:
        return ai_handler.get_default_ai()
    except Exception:
        return None

def _llm_answer(agent, user_query, system_prompt, render_pref=None):
    # UX rule: announce the AI call before it runs (flush so it shows
    # even when output is buffered).
    print(f"  Generating answer with {agent}…", flush=True)
    try:
        result = ai_handler.process_prompt(agent, user_query, system=system_prompt)
        # AIResponse unpacks as (payload, client, response, model).
        _, _, response, _ = result
        answer = ai_handler.get_content_auto(response).strip()
    except Exception as e:
        print(f"\n[LLM error: {e}]")
        print("Falling back to local lookup — retry with:")
        print(f'  st-ask --pseudo "{user_query}"')
        return
    _markdown.print_markdown(f"\n{answer}", render=render_pref)
    _print_link_block("See also:", _SEE_ALSO_LINKS, render_pref)

def _read_last_error():
    path = os.path.expanduser("~/.cross_api_cache/last_error.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    return data[-1]

def _explain_last_error(agent, system_prompt, render_pref=None):
    last = _read_last_error()
    if not last:
        print("No recent error recorded.")
        return
    # Breadcrumbs are scrubbed at write time; re-scrub defensively before
    # sending anything to the LLM (ASK-8 / ASK-15).
    error_text = scrub(
        f"Script: {last.get('script')}\n"
        f"Type: {last.get('exception_type')}\n"
        f"Message: {last.get('message')}"
    )
    prompt = (
        "Explain the following cross-st error to the user in plain language. "
        "State the most likely cause and give the exact command(s) to fix it:\n\n"
        f"{error_text}"
    )
    _llm_answer(agent, prompt, system_prompt, render_pref)

def _pseudo_answer(query, render_pref=None):
    """Render a Pseudo-AI (local lookup) answer for a single query."""
    matches = find_matches(query, _FAQ, top_k=3)
    if matches and matches[0]['_score'] > 0.6:
        _print_answer(matches[0], render_pref)
    elif matches and matches[0]['_score'] > 0.3:
        print("\nDid you mean:")
        for m in matches:
            print(f"  - {m['question']}")
        _markdown.print_muted(f"\n{FOOTER}", render=render_pref)
    else:
        _print_no_match(render_pref)

def main():
    # Load ~/.crossenv + project .env layers so API keys and DEFAULT_AGENT are
    # visible. st-ask deliberately bypasses require_config() (like st-admin /
    # st-man) so it can run before setup — but it still must load the env
    # layers to decide between the Pseudo-AI and Full-LLM tiers.
    mmd_startup.load_cross_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="*", help="Ask a question")
    parser.add_argument("--agent", help="Agent name to use for LLM tier")
    parser.add_argument("--pseudo", action="store_true", help="Force Pseudo-AI tier even if API key present")
    parser.add_argument("--explain-last-error", action="store_true", help="Explain the last error using the LLM tier")
    parser.add_argument("--no-render", action="store_true", help="Print raw markdown instead of rendered (styled) output")
    args = parser.parse_args()

    # Rendering preference: None = smart default (on in a TTY, raw when piped);
    # False = forced raw via --no-render.
    render_pref = False if args.no_render else None

    if args.explain_last_error:
        if _has_api_key() and not args.pseudo:
            agent = _select_agent(args)
            system_prompt = _build_system_prompt()
            if not agent or not system_prompt:
                print("LLM tier unavailable. Try again without --explain-last-error.")
                return 1
            _explain_last_error(agent, system_prompt, render_pref)
            return 0
        else:
            print("Pseudo-AI error explanation not implemented in this mode.")
            return 1

    if _has_api_key() and not args.pseudo:
        agent = _select_agent(args)
        system_prompt = _build_system_prompt()
        if not agent or not system_prompt:
            print("LLM tier unavailable. Remove your API key to use local FAQ help.")
            return 1
        if args.question:
            user_query = " ".join(args.question)
            _llm_answer(agent, user_query, system_prompt, render_pref)
            return 0
        # REPL for LLM tier
        print("st-ask (LLM): Type your question, :raw/:render to toggle rendering, or :quit to exit.")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q or q in (":quit", ":exit"): break
            if q == ":raw":
                render_pref = False
                print("  Rendering off (raw markdown).")
                continue
            if q == ":render":
                render_pref = True
                print("  Rendering on.")
                continue
            _llm_answer(agent, q, system_prompt, render_pref)
        return 0
    # Pseudo-AI tier
    if args.question:
        _pseudo_answer(" ".join(args.question), render_pref)
        return 0
    # REPL
    print("st-ask: Local FAQ help. Type your question, :raw/:render to toggle rendering, or :quit to exit.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q in (":quit", ":exit"): break
        if q == ":raw":
            render_pref = False
            print("  Rendering off (raw markdown).")
            continue
        if q == ":render":
            render_pref = True
            print("  Rendering on.")
            continue
        _pseudo_answer(q, render_pref)
    return 0

if __name__ == "__main__":
    sys.exit(main())
