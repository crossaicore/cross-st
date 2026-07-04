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


# ── Escape-hatch links (shown on every Full-LLM answer, per st-ask.md §1) ──
_WIKI_BASE = "https://github.com/crossaicore/cross-st/wiki"
_DISCOURSE_URL = "https://crossai.dev/c/help"
_ISSUES_URL = "https://github.com/crossaicore/cross-st/issues"

_LLM_SEE_ALSO = (
    "\nSee also:\n"
    f"  • Wiki:      {_WIKI_BASE}\n"
    f"  • Community: {_DISCOURSE_URL}\n"
    f"  • Issues:    {_ISSUES_URL}"
)

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
    "  5. End every answer with a 'See also:' block linking the most relevant "
    "wiki page(s).\n\n"
    "----- REFERENCE MATERIAL BEGINS -----\n"
    "{corpus}\n"
    "----- REFERENCE MATERIAL ENDS -----\n"
)

_FAQ = [
    {"id": "install", "question": "How do I install cross-st?", "answer": "Run: pipx install cross-st"},
    {"id": "upgrade", "question": "How do I upgrade cross-st?", "answer": "Run: st-admin --upgrade"},
    {"id": "api_key", "question": "How do I add an API key?", "answer": "Run: st-admin --setup and follow the prompts."},
    {"id": "help", "question": "Where can I get help?", "answer": "See https://github.com/crossaicore/cross-st/discussions or https://crossai.dev/community"},
    {"id": "uninstall", "question": "How do I uninstall cross-st?", "answer": "Run: pipx uninstall cross-st"},
]

FOOTER = "(local lookup — for full answers add an AI key with 'st-admin --setup')"


def _has_api_key():
    # Minimal: check for any known API key env var
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        if os.getenv(k):
            return True
    return False

def _print_answer(entry):
    print(f"\n{entry['answer']}")
    if entry.get('see_also'):
        print(f"See also: {entry['see_also']}")
    print(f"\n{FOOTER}")

def _print_no_match():
    print("\nI don’t have a canned answer for that. Try:")
    print("  • https://github.com/crossaicore/cross-st/discussions")
    print("  • https://crossai.dev/community")
    print("Starter questions:")
    for entry in _FAQ[:5]:
        print(f"  - {entry['question']}")
    print(f"\n{FOOTER}")

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

def _llm_answer(agent, user_query, system_prompt):
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
    print(f"\n{answer}")
    print(_LLM_SEE_ALSO)

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

def _explain_last_error(agent, system_prompt):
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
    _llm_answer(agent, prompt, system_prompt)

def _pseudo_answer(query):
    """Render a Pseudo-AI (local lookup) answer for a single query."""
    matches = find_matches(query, _FAQ, top_k=3)
    if matches and matches[0]['_score'] > 0.6:
        _print_answer(matches[0])
    elif matches and matches[0]['_score'] > 0.3:
        print("\nDid you mean:")
        for m in matches:
            print(f"  - {m['question']}")
        print(f"\n{FOOTER}")
    else:
        _print_no_match()

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
    args = parser.parse_args()

    if args.explain_last_error:
        if _has_api_key() and not args.pseudo:
            agent = _select_agent(args)
            system_prompt = _build_system_prompt()
            if not agent or not system_prompt:
                print("LLM tier unavailable. Try again without --explain-last-error.")
                return 1
            _explain_last_error(agent, system_prompt)
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
            _llm_answer(agent, user_query, system_prompt)
            return 0
        # REPL for LLM tier
        print("st-ask (LLM): Type your question, or :quit to exit.")
        while True:
            try:
                q = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q or q in (":quit", ":exit"): break
            _llm_answer(agent, q, system_prompt)
        return 0
    # Pseudo-AI tier
    if args.question:
        _pseudo_answer(" ".join(args.question))
        return 0
    # REPL
    print("st-ask: Local FAQ help. Type your question, or :quit to exit.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q or q in (":quit", ":exit"): break
        _pseudo_answer(q)
    return 0

if __name__ == "__main__":
    sys.exit(main())
