"""Web lookup for panel members, passed to `llm --functions`.

Panelists that cannot check anything invent instead: of six "measured" claims fact-checked
across two runs, four were fabricated, in the same confident register as the true ones.
Those fabrications were world facts — library versions, whether an API exists, what a cited
source actually says — which is exactly what these two tools cover.

Repo tools (list_files / read_file / grep_repo) lived here too and were removed. They cost
one real exposure incident, one silent false negative, and 0 usable answers out of 10
attempts across two tool-enabled runs. Three things must hold before they come back:

  1. built on `git ls-files` / `git grep`, not `pathlib.glob` — the glob version took 85s a
     call and answered "No matches" to `**/*.{md,ts}` because pathlib does not expand
     braces. A verification tool that lies is worse than none: it stamps a hallucination
     "checked". `git grep` did the same search correctly in 0.14s.
  2. one panel completes end to end with them enabled;
  3. that panel produces at least one finding the curated package did not already contain.

Keep every import in `import x` form. `llm --functions` execs this file into a bare
namespace and registers every non-underscore callable as a tool, so `from pathlib import
Path` silently handed the panel a `Path` constructor described as "can make system calls".
"""

import json
import os
import pathlib
import urllib.error
import urllib.request

WEB_RESULTS = 3            # results per search
WEB_CHARS = 2500           # per-result content cap
FETCH_CHARS = 12000        # one fetched page; raw pages run 30KB+
BUDGET = 192 * 1024        # total web bytes one panelist may pull

_spent = 0


def _web(endpoint: str, payload: dict):
    """POST to ollama's web API. Returns (data, error_message)."""
    global _spent
    keyfile = pathlib.Path(os.environ.get(
        "LLM_USER_PATH", pathlib.Path.home() / "Library/Application Support/io.datasette.llm"
    )) / "keys.json"
    try:
        key = json.loads(keyfile.read_text())["ollama"]
    except (OSError, KeyError, ValueError):
        return None, ("Web access unavailable: no 'ollama' key is stored. Answer from the "
                      "package alone, and mark anything you could not check.")
    if _spent >= BUDGET:
        return None, (f"Web budget of {BUDGET // 1024}KB is spent — nothing was fetched. "
                      f"Answer with what you have and say which points stayed unverified.")
    req = urllib.request.Request(
        f"https://ollama.com/api/{endpoint}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read()), None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        return None, f"Web request failed ({e}). Treat the claim as unverified, not as true."


def web_search(query: str) -> str:
    """Search the public web and return the top results as 'TITLE / URL / excerpt'.

    Use this to check any claim about the outside world — a library's current version,
    whether an API exists, what a source actually says. If the results do not support a
    claim you were about to make, say that instead of asserting it.
    """
    global _spent
    data, err = _web("web_search", {"query": query})
    if err:
        return err
    results = (data or {}).get("results", [])
    if not results:
        return f"No results for {query!r}. That absence is itself evidence — say so."
    out = []
    for r in results[:WEB_RESULTS]:
        body = (r.get("content") or "")[:WEB_CHARS]
        out.append(f"### {r.get('title','(no title)')}\n{r.get('url','')}\n\n{body}")
    text = "\n\n".join(out)
    _spent += len(text.encode())
    return text


def web_fetch(url: str) -> str:
    """Fetch one web page and return its text, given its URL.

    Use this to read a primary source directly — the doc page, the release notes, the
    actual passage behind a citation — rather than reasoning from search snippets about it.
    Quote what it says; if the page does not contain what you expected, report that.
    """
    global _spent
    data, err = _web("web_fetch", {"url": url})
    if err:
        return err
    if not data or data.get("error"):
        return (f"Could not fetch {url}: {(data or {}).get('error', 'no content')}. "
                f"Try web_search instead, or mark the point unverified.")
    body = (data.get("content") or "")[:FETCH_CHARS]
    _spent += len(body.encode())
    return f"### {data.get('title','(no title)')}\n{url}\n\n{body}"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.environ["LLM_USER_PATH"] = d                      # no keys.json in there
        assert "unavailable" in web_search("anything"), "missing key must not crash"
        assert "unavailable" in web_fetch("https://example.com"), "same for fetch"

        pathlib.Path(d, "keys.json").write_text(json.dumps({"ollama": "fake"}))
        _spent = BUDGET
        out = web_search("anything")
        assert "budget" in out and "nothing was fetched" in out, "must refuse when spent"

        ns = {}
        exec(pathlib.Path(__file__).read_text(), ns)         # exactly how llm loads this
        exposed = sorted(n for n, v in ns.items() if callable(v) and not n.startswith("_"))
        assert exposed == ["web_fetch", "web_search"], f"unexpected tools exposed: {exposed}"
        print("panel_tools self-check: ok")
