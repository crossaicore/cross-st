#!/usr/bin/env python3
"""
## st-fetch — Import external content into a container

Brings existing content into the Cross pipeline for fact-checking, improvement,
and publishing.  Content is stored as a data entry and immediately converted to
a report entry via st-prep (use --no-prep to store as raw data only).

Each fetched entry records its origin in make/model:
  make = "st-fetch"  (always)
  model = source type: "file", "clipboard", "x.com", or the URL domain
           e.g. "reddit.com", "bbc.co.uk", "en.wikipedia.org"

Sources supported:
  tweet_id    Fetch a post from X (Twitter) by numeric tweet ID
  --file      Import a plain text, markdown, or PDF file from disk
  --url       Import Markdown from a URL; convert HTML when Markdown is unavailable
  --clipboard Paste text directly from the system clipboard

```
st-fetch <tweet_id> file.json            # fetch X post by tweet ID
st-fetch --file report.md file.json      # import a local .txt or .md file
st-fetch --file report.pdf file.json     # import a PDF (requires pymupdf4llm)
st-fetch --url https://... file.json     # fetch a web page
st-fetch --clipboard file.json           # import text from clipboard
st-fetch --file report.md file.json --no-prep   # store raw data entry only
st-fetch <tweet_id> file.json --no-cache        # bypass cache, always fetch live
```

Full pipeline for refreshing an existing report:
  st-fetch --file old_report.md old_report.json
  st-bang old_report.json          # regenerate with all 5 AI
  st-cross old_report.json         # cross-product fact-check
  st-merge old_report.json         # synthesize best version
  st-post --site myblog old_report.json

Requirements:
  X_COM_BEARER_TOKEN=<bearer token>  in .env   (tweet_id source only)

Options: --file  --url  --clipboard  --no-prep  --no-cache  -v  -q

PDF import uses pymupdf4llm (lazy import — only required when fetching PDFs):
  pip install pymupdf4llm          # venv / plain pip install
  pipx inject cross-st pymupdf4llm # pipx install
"""

from _report_store import load_snapshot, save_snapshot, ensure_data_id
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from urllib.parse import urljoin, urlsplit
from mmd_startup import load_cross_env, require_config


from ai_url import get_url_cached_response, get_title, get_story, AI_MAKE, AI_MODEL
from mmd_branding import get_app_tag
from mmd_process_report import remove_markdown


def _fetch_tweet(tweet_id, verbose, use_cache):
    """Fetch a tweet by ID. Returns (title, text, raw_response)."""
    response = get_url_cached_response(tweet_id, verbose, use_cache)
    title = get_title(response) or f"Tweet {tweet_id}"
    text  = get_story(response) or ""
    return title, text, response


def _extract_pdf(filepath, verbose):
    """Extract content from a PDF file. Returns (title, text, markdown, response).

    Uses pymupdf4llm for Markdown-quality extraction. Falls back gracefully for
    scanned/image-only PDFs by warning the user. Lazy-imports the library so that
    users who never use PDF import don't need it installed.
    """
    try:
        import pymupdf4llm
        import pymupdf  # bundled with pymupdf4llm
    except ImportError:
        print("  PDF support not installed — installing now (one-time, ~22 MB)…", flush=True)
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "pymupdf4llm"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print("Error: automatic install of pymupdf4llm failed.")
            print(result.stderr[-600:].strip() if result.stderr else "(no output)")
            print()
            print("Install manually and re-run:")
            if "pipx" in sys.executable:
                print('  pipx install --force "cross-st[pdf]"')
                print("  or: pipx inject cross-st pymupdf4llm")
            else:
                print('  pip install "cross-st[pdf]"')
            sys.exit(1)
        # Retry imports after successful install
        import pymupdf4llm  # noqa: F811
        import pymupdf      # noqa: F811
        print("  PDF support installed. ✓", flush=True)

    # Open document to grab metadata and page count
    doc = pymupdf.open(filepath)
    num_pages = len(doc)
    meta = doc.metadata or {}

    # Extract Markdown via pymupdf4llm
    md = pymupdf4llm.to_markdown(filepath)

    # Warn if extraction looks empty (likely scanned PDF)
    plain_chars = len(md.strip())
    if plain_chars < 50:
        print(f"  Warning: very little text extracted ({plain_chars} chars) — "
              "PDF may be scanned/image-based. Try OCR first (tesseract, Adobe Acrobat).")

    # Determine title: PDF metadata → first # heading → first non-empty line → filename
    title = (meta.get("title") or "").strip()
    if not title:
        for line in md.splitlines():
            stripped = line.strip().lstrip('#').strip()
            if stripped:
                title = stripped[:120]
                break
    title = title or os.path.basename(filepath)

    text = remove_markdown(md)

    response = {
        "source": "file",
        "filepath": filepath,
        "format": "pdf",
        "pages": num_pages,
        "raw": md,
    }
    if verbose:
        print(f"  Extracted {plain_chars} chars ({num_pages} pages) from {filepath}")
    return title, text, md, response


def _is_pdf(filepath):
    """Return True if filepath is a PDF (extension OR magic bytes)."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        return True
    try:
        with open(filepath, 'rb') as f:
            return f.read(4) == b'%PDF'
    except OSError:
        return False


def _fetch_file(filepath, verbose):
    """Import a plain text, markdown, or PDF file from disk. Returns (title, text, raw_response)."""
    if not os.path.isfile(filepath):
        print(f"Error: file not found: {filepath}")
        sys.exit(1)

    if _is_pdf(filepath):
        title, text, md, response = _extract_pdf(filepath, verbose)
        # markdown field gets rich MD; text is plain; source_model hint returned via response
        response["_source_model"] = "pdf"
        return title, text, response

    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()
    # Use first non-empty line as title candidate; strip markdown heading markers
    title = ""
    for line in raw.splitlines():
        line = line.strip().lstrip('#').strip()
        if line:
            title = line[:120]
            break
    title = title or os.path.basename(filepath)
    text  = remove_markdown(raw)
    response = {"source": "file", "filepath": filepath, "raw": raw}
    if verbose:
        print(f"  Loaded {len(raw)} chars from {filepath}")
    return title, text, response


def _is_markdown_response(response):
    media_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return media_type in {"text/markdown", "text/x-markdown"} or (
        media_type in {"text/plain", "application/octet-stream", ""}
        and urlsplit(response.url).path.lower().endswith((".md", ".markdown"))
    )


def _markdown_url_result(response, requested_url, title=None):
    """Keep the complete Markdown response; derive plain text separately."""
    raw = response.text
    if not title:
        heading = re.search(r"^#\s+(.+?)\s*#*\s*$", raw, re.MULTILINE)
        title = (heading.group(1) if heading else next(
            (line.strip() for line in raw.splitlines() if line.strip()), requested_url))
        title = remove_markdown(title)[:120]
    return title, remove_markdown(raw), {
        "source": "url", "url": requested_url, "fetched_url": response.url,
        "status_code": response.status_code, "format": "markdown", "raw": raw,
    }


def _html_markdown(soup, base_url):
    try:
        from markdownify import markdownify
    except ImportError:
        print("  HTML-to-Markdown support not installed — installing now (one-time)…", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "markdownify>=1.2"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise SystemExit("Error: auto-install of markdownify failed.\n" +
                             (result.stderr or "(no output)")[-400:].strip())
        from markdownify import markdownify
        print("  HTML-to-Markdown support installed. ✓", flush=True)

    base = soup.find("base", href=True)
    if base:
        base_url = urljoin(base_url, base["href"])
    # Keep visible content, including links inside article headers and footers.
    for tag in soup(["script", "style"]):
        tag.decompose()
    for tag in soup.find_all(True):
        for attribute in ("href", "src", "poster"):
            if tag.get(attribute):
                tag[attribute] = urljoin(base_url, tag[attribute])
    return markdownify(str(soup.body or soup), heading_style="ATX",
                       keep_inline_images_in=["a", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6"])


def _fetch_url(url, verbose, *, quiet=False):
    """Prefer source Markdown, otherwise convert HTML without discarding links."""
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; cross-fetch/1.0)",
               "Accept": "text/markdown, text/html;q=0.9, text/plain;q=0.8, */*;q=0.1"}
    if verbose:
        print(f"  Fetching URL: {url}")
    try:
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
    except requests.RequestException as error:
        raise SystemExit(f"Error fetching URL: {error}") from error

    if _is_markdown_response(resp):
        return _markdown_url_result(resp, url)

    # Plain-text sources must not be parsed as HTML (which can eat <...> text).
    if resp.headers.get("Content-Type", "").split(";")[0].strip().lower() == "text/plain":
        title, text, response = _markdown_url_result(resp, url)
        response["format"] = "text"
        return title, text, response

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  Web scraping support not installed — installing now (one-time, ~1 MB)…", flush=True)
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "beautifulsoup4"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print("Error: auto-install of beautifulsoup4 failed.")
            print(result.stderr[-400:].strip() if result.stderr else "(no output)")
            sys.exit(1)
        from bs4 import BeautifulSoup  # noqa: F811
        print("  Web scraping support installed. ✓", flush=True)

    soup = BeautifulSoup(resp.text, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    # Prefer <h1> as title
    h1 = soup.find("h1")
    if h1:
        page_title = h1.get_text(" ", strip=True) or page_title

    alternate = soup.find("link", rel="alternate", type="text/markdown", href=True)
    if alternate:
        markdown_url = urljoin(resp.url, alternate["href"])
        if urlsplit(markdown_url).scheme in {"http", "https"}:
            try:
                markdown_response = requests.get(markdown_url, timeout=15, headers=headers)
                markdown_response.raise_for_status()
                if _is_markdown_response(markdown_response):
                    return _markdown_url_result(markdown_response, url, page_title or None)
            except requests.RequestException:
                pass
            if not quiet:
                print("  Markdown version unavailable; converting the HTML page instead.", flush=True)

    markdown = _html_markdown(soup, resp.url)
    response = {"source": "url", "url": url, "fetched_url": resp.url,
                "status_code": resp.status_code, "format": "html",
                "raw": markdown, "html": resp.text}
    return page_title or url, remove_markdown(markdown), response


def _fetch_clipboard(verbose):
    """Read text from the system clipboard. Returns (title, text, raw_response).

    Uses pbpaste on macOS, xclip/xsel on Linux, and PowerShell on Windows.
    Falls back to reading stdin if no clipboard tool is found.
    """
    import platform
    import subprocess as _sp

    system = platform.system()
    raw = ""

    try:
        if system == "Darwin":
            result = _sp.run(["pbpaste"], capture_output=True, text=True, check=True)
            raw = result.stdout
        elif system == "Linux":
            # Try xclip first, then xsel
            for cmd in [["xclip", "-selection", "clipboard", "-o"],
                        ["xsel", "--clipboard", "--output"]]:
                try:
                    result = _sp.run(cmd, capture_output=True, text=True, check=True)
                    raw = result.stdout
                    break
                except (FileNotFoundError, _sp.CalledProcessError):
                    continue
            if not raw:
                print("Error: clipboard tool not found. Install xclip or xsel.")
                print("  sudo apt install xclip")
                import sys as _sys
                _sys.exit(1)
        elif system == "Windows":
            result = _sp.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, check=True
            )
            raw = result.stdout
        else:
            print(f"Error: clipboard not supported on {system}")
            import sys as _sys
            _sys.exit(1)
    except Exception as e:
        print(f"Error reading clipboard: {e}")
        import sys as _sys
        _sys.exit(1)

    if not raw.strip():
        print("Error: clipboard is empty")
        import sys as _sys
        _sys.exit(1)

    if verbose:
        print(f"  Read {len(raw)} chars from clipboard")

    # Infer title from first non-empty line
    title = ""
    for line in raw.splitlines():
        line = line.strip().lstrip('#').strip()
        if line:
            title = line[:120]
            break
    title = title or "Clipboard import"

    text = remove_markdown(raw)
    response = {"source": "clipboard", "raw": raw}
    return title, text, response


def main():
    require_config()
    parser = argparse.ArgumentParser(
        prog='st-fetch',
        description='Import external content into a Cross container')

    # Source — mutually exclusive: tweet_id positional, --file, --url, or --clipboard
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--file', type=str, metavar='PATH',
                               help='Import a plain text, markdown, or PDF file from disk')
    source_group.add_argument('--url', type=str, metavar='URL',
                               help='Import Markdown or convert HTML, preserving links and formatting')
    source_group.add_argument('--clipboard', action='store_true',
                               help='Import text from the system clipboard')

    parser.add_argument('tweet_id', type=str, nargs='?', default=None,
                        help='Tweet ID to fetch from X (numeric ID from post URL)')
    parser.add_argument('json_file', type=str,
                        help='Path to the .json container', metavar='file.json')
    parser.add_argument('--cache', dest='cache', action='store_true', default=True,
                        help='Enable API cache (default: on)')
    parser.add_argument('--no-cache', dest='cache', action='store_false',
                        help='Disable API cache — always fetch live')
    parser.add_argument('--prep', dest='prep', action='store_true', default=True,
                        help='Run st-prep after fetching (default: on)')
    parser.add_argument('--no-prep', dest='prep', action='store_false',
                        help='Skip st-prep — store as raw data entry only')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose output')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Minimal output')
    args = parser.parse_args()

    # Validate: exactly one source must be given
    if not args.file and not args.url and not args.clipboard and not args.tweet_id:
        parser.error("Specify a tweet_id, --file PATH, --url URL, or --clipboard")

    file_prefix = args.json_file.rsplit('.', 1)[0]
    file_json   = file_prefix + ".json"

    load_cross_env()

    # ── Fetch from source ─────────────────────────────────────────────────────
    source_make  = AI_MAKE    # "url"
    source_model = AI_MODEL   # "bs4"
    source_id    = None

    if args.file:
        if not args.quiet:
            print(f"  Importing file: {args.file}…", end='', flush=True)
        title, text, response = _fetch_file(args.file, args.verbose)
        source_model = response.pop("_source_model", "file")
        if not args.quiet:
            print(" ✓")

    elif args.url:
        if not args.quiet:
            print(f"  Fetching URL…", end='', flush=True)
        title, text, response = _fetch_url(args.url, args.verbose, quiet=args.quiet)
        # Use the domain as the model (e.g. "reddit.com", "bbc.co.uk")
        from urllib.parse import urlparse
        _netloc = urlparse(args.url).netloc.lower()
        source_model = _netloc.lstrip("www.") or "web"
        if not args.quiet:
            print(" ✓")

    elif args.clipboard:
        if not args.quiet:
            print(f"  Reading clipboard…", end='', flush=True)
        title, text, response = _fetch_clipboard(args.verbose)
        source_model = "clipboard"
        if not args.quiet:
            print(" ✓")

    else:
        # tweet_id source — requires bearer token
        if not os.getenv("X_COM_BEARER_TOKEN"):
            print("Error: X_COM_BEARER_TOKEN not set in .env")
            print("  Obtain a bearer token from developer.x.com and add:")
            print("  X_COM_BEARER_TOKEN=<your token>")
            sys.exit(1)
        cache_note = "cache" if args.cache else "live"
        if not args.quiet:
            print(f"  Fetching tweet {args.tweet_id} ({cache_note})…", end='', flush=True)
        try:
            title, text, response = _fetch_tweet(args.tweet_id, args.verbose, args.cache)
        except Exception as e:
            print(f"\nError fetching tweet {args.tweet_id}: {e}")
            sys.exit(1)
        source_model = "x.com"
        if not args.quiet:
            print(" ✓")

    if args.verbose:
        print(json.dumps(response, indent=2))

    if not text:
        print(f"  Warning: no text content found in source")

    if not args.quiet:
        print(f"  {title[:72]}")

    # ── Load or create container ──────────────────────────────────────────────
    container_modified = False
    if os.path.isfile(file_json):
        try:
            container, file_fingerprint = load_snapshot(file_json)
        except json.JSONDecodeError:
            print(f"Error: {file_json} contains invalid JSON.")
            sys.exit(1)
        except Exception as e:
            print(f"An unexpected error occurred reading {file_json}: {e}")
            sys.exit(1)
    else:
        container = {"data": [], "story": []}
        file_fingerprint = None
        if not args.quiet:
            print(f"  Creating new container: {file_json}")

    # ── Build data entry ──────────────────────────────────────────────────────
    ai_tag = get_app_tag() + f"{source_make}:{source_model}"
    # Preserve source Markdown for URLs, files, PDFs, and clipboard imports.
    markdown_content = response.get("raw", text)
    data = {
        "make":         source_make,
        "model":        source_model,
        # VRD-10h: data[] entries are always "author" — st-fetch sourced
        # documents are treated as authored content for downstream scoring.
        "role":         "author",
        "title":        title,
        "text":         text,
        "markdown":     markdown_content,
        "tag":          ai_tag,
        "gen_response": response,
    }
    data_str = json.dumps(data, sort_keys=True)
    data["md5_hash"] = hashlib.md5(data_str.encode('utf-8')).hexdigest()

    # ── Deduplicate ───────────────────────────────────────────────────────────
    duplicate = next(
        (i + 1 for i, d in enumerate(container.get("data", []))
         if d.get("md5_hash") == data["md5_hash"]),
        None
    )
    if duplicate is None:
        ensure_data_id(data)
        container.setdefault("data", []).append(data)
        container_modified = True
        data_index = len(container["data"])
        if not args.quiet:
            print(f"  Added as data entry {data_index}")
    else:
        data_index = duplicate
        if not args.quiet:
            print(f"  Already in container as data entry {duplicate} — not added")

    # ── Save container ────────────────────────────────────────────────────────
    if container_modified:
        save_snapshot(file_json, container, file_fingerprint)
        if not args.quiet:
            print(f"  Container updated: {file_json}")

    # ── Optional st-prep pass ─────────────────────────────────────────────────
    if args.prep and container_modified:
        if not args.quiet:
            print(f"  Running st-prep on data entry {data_index}…")
        subprocess.run(
            ["st-prep", "-d", str(data_index), file_json],
            check=False
        )


if __name__ == "__main__":
    main()

