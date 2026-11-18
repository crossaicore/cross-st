"""URL imports retain Markdown and links without live network or AI calls."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests


def command(name):
    path = Path(__file__).parents[1] / "cross_st" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(body, media_type="text/markdown; charset=utf-8", url="https://example.test/report"):
    return SimpleNamespace(text=body, headers={"Content-Type": media_type}, url=url,
                           status_code=200, raise_for_status=lambda: None)


@pytest.fixture
def fetch(monkeypatch):
    module = command("st-fetch")
    monkeypatch.setattr(module, "load_cross_env", lambda: None)
    monkeypatch.setattr(module, "require_config", lambda: None)
    return module


MARKDOWN = """# Green Bean Casserole

![Casserole](https://example.test/photo.jpeg)

**Original recipe:** [Delish](https://www.delish.com/recipe/)

## Ingredients

- Green beans
- **Butter** and *onions*

| Item | Amount |
| --- | --- |
| Milk | 3 cups |

> Keep this quotation.

---

Directions
==========

1. Bake.
2. Serve.

```text
<tag> and #literal
---
```

Keep the final blank lines.

"""


@pytest.mark.parametrize("media_type,url", [
    ("text/markdown; charset=utf-8", "https://example.test/report"),
    ("text/x-markdown", "https://example.test/report"),
    ("text/plain", "https://example.test/report.md?download=1"),
    ("application/octet-stream", "https://example.test/report.markdown"),
])
def test_native_markdown_preserved_exactly(fetch, monkeypatch, media_type, url):
    get = Mock(return_value=response(MARKDOWN, media_type, url))
    monkeypatch.setattr(requests, "get", get)
    title, text, source = fetch._fetch_url(url, False)
    assert title == "Green Bean Casserole"
    assert source["raw"] == MARKDOWN
    assert source["format"] == "markdown"
    assert source["url"] == url
    assert "Ingredients" in text
    assert get.call_count == 1
    assert get.call_args.kwargs["headers"]["Accept"].startswith("text/markdown")


def test_follows_advertised_markdown_after_redirect(fetch, monkeypatch):
    pytest.importorskip("bs4")
    html = '<html><head><link rel="alternate nofollow" type="text/markdown" href="report.md"></head><body><h1>Green Bean Casserole</h1></body></html>'
    get = Mock(side_effect=[response(html, "text/html", "https://example.test/topics/report"),
                           response(MARKDOWN, url="https://example.test/topics/report.md")])
    monkeypatch.setattr(requests, "get", get)
    title, _, source = fetch._fetch_url("https://example.test/redirect", False)
    assert title == "Green Bean Casserole"
    assert source["raw"] == MARKDOWN
    assert source["url"] == "https://example.test/redirect"
    assert source["fetched_url"] == "https://example.test/topics/report.md"
    assert get.call_args_list[1].args[0] == source["fetched_url"]


@pytest.mark.parametrize("failure", ["http", "html"])
def test_unavailable_markdown_converts_html_without_losing_links(fetch, monkeypatch, capsys, failure):
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    html = """<html><head><title>Recipe</title>
    <link rel="alternate" type="text/markdown" href="report.md">
    <base href="https://example.test/recipes/"></head><body>
    <h1>Green Bean Casserole</h1><header><a href="https://www.delish.com/recipe/">Delish</a></header>
    <p><strong>Butter</strong> and <em>onions</em></p>
    <ul><li>Green beans</li><li>Milk</li></ul><blockquote>A quotation</blockquote>
    <img alt="Casserole" src="photo.jpeg"><a href="../notes">Notes</a>
    <table><tr><th>Amount</th><th>Item</th></tr><tr><td>3 cups</td><td>Milk</td></tr></table>
    <pre><code>print('recipe')</code></pre><hr><footer>Footer content</footer>
    <script>tracking_noise()</script><style>.noise{}</style></body></html>"""
    alternate = requests.HTTPError("Not found") if failure == "http" else response(
        "<html>Not Markdown</html>", "text/html", "https://example.test/report.md")
    get = Mock(side_effect=[response(html, "text/html"), alternate])
    monkeypatch.setattr(requests, "get", get)
    title, _, source = fetch._fetch_url("https://example.test/report", False)
    md = source["raw"]
    assert title == "Green Bean Casserole"
    for expected in ("# Green Bean Casserole", "[Delish](https://www.delish.com/recipe/)",
                     "**Butter**", "*onions*", "* Green beans", "> A quotation",
                     "![Casserole](https://example.test/recipes/photo.jpeg)",
                     "[Notes](https://example.test/notes)", "| Amount | Item |",
                     "```", "print('recipe')", "---", "Footer content"):
        assert expected in md
    assert "tracking_noise" not in md
    assert source["html"] == html
    assert "converting the HTML" in capsys.readouterr().out


def test_plain_text_keeps_angle_brackets(fetch, monkeypatch):
    body = "A plain report\nPreserve <important> content.\n"
    monkeypatch.setattr(requests, "get", Mock(return_value=response(body, "text/plain")))
    _, _, source = fetch._fetch_url("https://example.test/report", False)
    assert source["raw"] == body
    assert source["format"] == "text"


def test_native_markdown_needs_no_html_dependencies(fetch, monkeypatch):
    monkeypatch.setitem(sys.modules, "bs4", None)
    monkeypatch.setitem(sys.modules, "markdownify", None)
    monkeypatch.setattr(requests, "get", Mock(return_value=response(MARKDOWN)))
    install = Mock(side_effect=AssertionError("Native Markdown must not install HTML packages"))
    monkeypatch.setattr(fetch.subprocess, "run", install)
    assert fetch._fetch_url("https://example.test/report", False)[2]["raw"] == MARKDOWN
    install.assert_not_called()


def test_missing_converter_install_failure_does_not_save_plain_text(fetch, monkeypatch):
    bs4 = pytest.importorskip("bs4")
    monkeypatch.setitem(sys.modules, "markdownify", None)
    install = Mock(return_value=SimpleNamespace(returncode=1, stderr="Installation unavailable"))
    monkeypatch.setattr(fetch.subprocess, "run", install)
    with pytest.raises(SystemExit, match="auto-install of markdownify failed"):
        fetch._html_markdown(bs4.BeautifulSoup("<p>Content</p>", "html.parser"), "https://example.test/")
    assert install.call_args.args[0][:4] == [sys.executable, "-m", "pip", "install"]


@pytest.mark.parametrize("source_type", ["url", "file", "clipboard"])
def test_markdown_survives_fetch_prep_and_export(fetch, monkeypatch, tmp_path, source_type):
    prep = command("st-prep")
    monkeypatch.setattr(prep, "load_cross_env", lambda: None)
    monkeypatch.setattr(prep, "require_config", lambda: None)
    path = tmp_path / "report.json"
    if source_type == "url":
        monkeypatch.setattr(requests, "get", Mock(return_value=response(MARKDOWN)))
        flags = ["--url", "https://example.test/report"]
    elif source_type == "file":
        source = tmp_path / "source.md"
        source.write_text(MARKDOWN)
        flags = ["--file", str(source)]
    else:
        monkeypatch.setattr(fetch, "_fetch_clipboard", lambda *_: (
            "Green Bean Casserole", "Plain text", {"source": "clipboard", "raw": MARKDOWN}))
        flags = ["--clipboard"]

    def run_prep(argv, **kwargs):
        assert argv[:3] == ["st-prep", "-d", "1"]
        with monkeypatch.context() as context:
            context.setattr(prep.sys, "argv", [*argv, "--markdown"])
            prep.main()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(fetch.subprocess, "run", run_prep)
    monkeypatch.setattr(fetch.sys, "argv", ["st-fetch", *flags, str(path)])
    fetch.main()
    saved = json.loads(path.read_text())
    assert saved["data"][0]["markdown"] == MARKDOWN
    assert saved["data"][0]["gen_response"]["raw"] == MARKDOWN
    expected = MARKDOWN + "\n\n" + prep.get_tagline_for_reading(
        saved["data"][0]["make"], saved["data"][0]["model"])
    assert saved["story"][0]["markdown"] == expected
    assert path.with_suffix(".md").read_text() == expected
    assert saved["story"][0]["title"] == "Green Bean Casserole"
