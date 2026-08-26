"""Lookup tools for panel members, passed to `llm --functions`.

Two families, and they answer to different failure modes.

WEB (`web_search` / `web_fetch`). Panelists that cannot check anything invent instead: of
six "measured" claims fact-checked across two runs, four were fabricated, in the same
confident register as the true ones. Those fabrications were world facts — library
versions, whether an API exists, what a cited source actually says.

REPO (`list_files` / `read_file` / `grep_repo`). These shipped once, were withdrawn, and
are back — rebuilt, not restored. The first version failed twice, and the two failures
have different lessons:

  * It used a prefix deny-list to hide secrets, and a `.worktrees/` copy of the tree walked
    straight around it: 96 excluded files were read. The lesson is not "don't read the
    repo" — for an open-source project whose code is being pasted into these same APIs
    anyway, that objection is weak. The lesson is that **a deny-list is the wrong shape.**
    This version has no deny-list. Visibility is defined positively by `git ls-files`, so
    only tracked files exist at all; `.env`, keystores, build output and stray worktree
    copies are invisible because they are untracked, not because a pattern caught them.
    A path that is not in `git ls-files` cannot be read, no matter how it is spelled.

  * It searched with `pathlib.glob`, which does not expand `{a,b}`, so an 85-second search
    answered "No matches" for text that was plainly present. That one is the real hazard:
    **a verification tool that lies is worse than none — it stamps a hallucination
    "checked."** `git grep` ran the same query correctly in 0.14s and is what runs here.

The repo root comes from PANEL_REPO, exported by the skill before the fan-out. The panel
runs with its cwd inside the archive directory, so without it there is no repo in scope —
in which case these tools say so plainly rather than guessing at a path.

Keep every import in `import x` form. `llm --functions` execs this file into a bare
namespace and registers every non-underscore callable as a tool, so `from pathlib import
Path` silently handed the panel a `Path` constructor described as "can make system calls".
"""

import json
import os
import pathlib
import subprocess
import urllib.error
import urllib.parse
import urllib.request

WEB_RESULTS = 3            # results per search
WEB_CHARS = 2500           # per-result content cap
FETCH_CHARS = 12000        # one fetched page; raw pages run 30KB+
BUDGET = 192 * 1024        # total web bytes one panelist may pull

FILE_CHARS = 60000         # one source file; longer ones are truncated, and say so
GREP_LINES = 80            # matching lines returned per grep
LIST_FILES = 400           # paths returned per listing
REPO_BUDGET = 512 * 1024   # total repo bytes one panelist may pull

_spent = 0
_repo_spent = 0


def _cfg() -> pathlib.Path:
    """llm's config directory — where keys, model aliases and these tools all live."""
    return pathlib.Path(os.environ.get(
        "LLM_USER_PATH", pathlib.Path.home() / "Library/Application Support/io.datasette.llm"))


def _key(name: str):
    """Read one stored llm key. Returns None when it isn't there."""
    try:
        return json.loads((_cfg() / "keys.json").read_text())[name]
    except (OSError, KeyError, ValueError):
        return None


DEFAULT_BACKENDS = [
    {"name": "brave", "key": "brave",
     "url": "https://api.search.brave.com/res/v1/web/search?extra_snippets=true&q={q}",
     "header": {"X-Subscription-Token": "{key}", "Accept": "application/json"},
     "results": "web.results", "title": "title", "link": "url",
     "content": ["description", "extra_snippets"]},
    {"name": "ollama", "key": "ollama",
     "url": "https://ollama.com/api/web_search",
     "method": "POST", "body": {"query": "{q}"},
     "header": {"Authorization": "Bearer {key}", "Content-Type": "application/json"},
     "results": "results", "title": "title", "link": "url", "content": ["content"]},
]


def _backends():
    """Search backends, in the order they are tried. Editable, like the model table.

    Lives in `panel-search.json` beside the model aliases. Same idea as
    extra-openai-models.yaml: which provider answers a search is a configuration choice,
    not something baked into this file. Missing or malformed file falls back to the two
    built-in entries, so an install that never touches it behaves exactly as before.
    """
    f = _cfg() / "panel-search.json"
    try:
        entries = json.loads(f.read_text())
        return entries if isinstance(entries, list) and entries else DEFAULT_BACKENDS
    except (OSError, ValueError):
        return DEFAULT_BACKENDS


def _dig(data, path: str):
    """Walk a dotted path: 'web.results' -> data['web']['results']. [] when absent."""
    for part in path.split("."):
        if not isinstance(data, dict):
            return []
        data = data.get(part)
    return data if isinstance(data, list) else []


def _search_one(b: dict, query: str):
    """Run one backend. Returns (results, error); results is [] when it found nothing,
    and None when the backend is not configured at all."""
    key = _key(b.get("key", ""))
    if not key:
        return None, None                      # not configured; caller falls through
    fill = lambda t: t.replace("{q}", urllib.parse.quote(query)).replace("{key}", key)
    headers = {k: v.replace("{key}", key) for k, v in (b.get("header") or {}).items()}
    body = None
    if b.get("method", "GET").upper() == "POST":
        raw = json.dumps(b.get("body") or {}).replace("{q}", query.replace('"', '\\"'))
        body = raw.encode()
    req = urllib.request.Request(fill(b["url"]), data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, KeyError) as e:
        return None, f"{b.get('name','backend')} search failed ({e})"
    out = []
    for r in _dig(data, b.get("results", "results"))[:WEB_RESULTS]:
        if not isinstance(r, dict):
            continue
        parts = []
        for f in b.get("content", ["content"]):
            v = r.get(f)
            parts.extend(v if isinstance(v, list) else [v] if v else [])
        out.append({"title": r.get(b.get("title", "title")) or "(no title)",
                    "url": r.get(b.get("link", "url")) or "",
                    "content": " ".join(str(x) for x in parts)[:WEB_CHARS]})
    return out, None


def _web(endpoint: str, payload: dict):
    """POST to ollama's web API. Returns (data, error_message)."""
    global _spent
    key = _key("ollama")
    if key is None:
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


def _git(*args, timeout: int = 30):
    """Run one git command inside PANEL_REPO. Returns (stdout, error_message)."""
    root = os.environ.get("PANEL_REPO", "").strip()
    if not root:
        return None, ("No repository is in scope for this panel (PANEL_REPO is unset), so "
                      "the source cannot be consulted. Answer from the package alone and "
                      "say which points you could not check against the code.")
    try:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"git failed ({e}). Treat the point as unchecked, not as absent."
    if p.returncode not in (0, 1):          # 1 = "no matches" for grep, which is a real answer
        return None, (f"git exited {p.returncode}: {p.stderr.strip()[:300]}. "
                      f"Treat the point as unchecked.")
    return p.stdout, None


def _pathspecs(pattern: str):
    """Expand one brace group into separate pathspecs: 'a/*.{ts,md}' -> two patterns.

    Neither git pathspec nor pathlib expands braces — the shell does. The first version of
    these tools passed `**/*.{md,ts}` straight through and spent 85 seconds answering "No
    matches" about text that was present. A tool that reports a false absence is worse than
    no tool, so the expansion happens here rather than not at all.
    """
    if "{" not in pattern or "}" not in pattern:
        return [pattern] if pattern else []
    head, rest = pattern.split("{", 1)
    body, tail = rest.split("}", 1)
    return [f"{head}{alt}{t}" for alt in body.split(",") for t in _pathspecs(tail) or [""]]


def _tracked(path: str):
    """True only if `path` is a file tracked by git. This is the whole access rule."""
    out, err = _git("ls-files", "--error-unmatch", "--", path)
    return (out is not None and out.strip() != ""), err


def web_search(query: str) -> str:
    """Search the public web and return the top results as 'TITLE / URL / excerpt'.

    Use this to check any claim about the outside world — a library's current version,
    whether an API exists, what a source actually says. If the results do not support a
    claim you were about to make, say that instead of asserting it. **Read the result before
    searching again**: repeating a query you have already run in slightly different words
    spends your budget without adding anything. When you have the answer, move on.
    """
    global _spent
    if _spent >= BUDGET:                       # one gate for every backend
        return (f"Web budget of {BUDGET // 1024}KB is spent — nothing was fetched. "
                f"Answer with what you have and say which points stayed unverified.")

    tried, configured = [], 0
    for b in _backends():
        results, err = _search_one(b, query)
        if results is None and err is None:
            continue                           # backend not configured — silent skip
        configured += 1
        if err:
            tried.append(err)
            continue
        if not results:
            tried.append(f"{b.get('name','backend')} returned no results")
            continue
        text = "\n\n".join(f"### {r['title']}\n{r['url']}\n\n{r['content']}" for r in results)
        _spent += len(text.encode())
        note = f" after: {'; '.join(tried)}" if tried else ""
        return f"(index: {b.get('name','?')}{note})\n\n{text}"

    if not configured:
        return ("Web search is unavailable: none of the configured backends has a stored key. "
                "Answer from the package alone, and mark anything you could not check.")
    return (f"Nothing found for {query!r} — {'; '.join(tried)}. Every index available here "
            f"was queried and came back empty. Report that as a search that found nothing, "
            f"not as proof the thing does not exist.")


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


def list_files(pattern: str = "") -> str:
    """List files tracked by git in the project, optionally filtered by a glob pattern.

    Pattern is a git pathspec, e.g. 'src/**/*.ts' or 'docs/adr/*.md'; leave it empty to see
    the whole tree. Only tracked files are visible — anything untracked or gitignored does
    not exist as far as these tools are concerned. Use this to find out what is actually in
    the project before assuming a file exists.
    """
    specs = _pathspecs(pattern)
    global _repo_spent
    args = ["ls-files"] + (["--", *specs] if specs else [])
    out, err = _git(*args)
    if err:
        return err
    paths = [p for p in out.splitlines() if p]
    if not paths:
        return (f"No tracked files match {pattern!r}. Either the pattern is wrong or the "
                f"file is untracked — do not conclude the functionality is missing from "
                f"this alone; say the search came back empty.")
    head = paths[:LIST_FILES]
    _repo_spent += sum(len(p.encode()) + 1 for p in head)
    note = "" if len(paths) <= LIST_FILES else \
        f"\n\n({len(paths)} matches, {LIST_FILES} shown — narrow the pattern to see the rest.)"
    return "\n".join(head) + note


def read_file(path: str) -> str:
    """Read one tracked file from the project and return it with line numbers.

    Line numbers are included so you can cite a claim as `path:line`. Only files tracked by
    git can be read. Quote what the file says; if it does not contain what you expected,
    report that rather than reasoning about what it probably contains.
    """
    global _repo_spent
    if _repo_spent >= REPO_BUDGET:
        return (f"Repo budget of {REPO_BUDGET // 1024}KB is spent — nothing was read. "
                f"Answer with what you have and say which points stayed unverified.")
    ok, err = _tracked(path)
    if err:
        return err
    if not ok:
        return (f"{path!r} is not a tracked file in this repository. Check the path with "
                f"list_files. Do not treat this as proof the file's contents do not exist.")
    out, err = _git("show", f"HEAD:{path}", timeout=20)
    if err:
        return err
    body = out or ""
    truncated = len(body) > FILE_CHARS
    body = body[:FILE_CHARS]
    _repo_spent += len(body.encode())
    lines = body.splitlines()
    numbered = "\n".join(f"{i:>5}\t{ln}" for i, ln in enumerate(lines, 1))
    tail = f"\n\n(truncated at {FILE_CHARS} chars — use grep_repo to reach the rest.)" \
        if truncated else ""
    return f"### {path}\n\n{numbered}{tail}"


def grep_repo(pattern: str, path_pattern: str = "") -> str:
    """Search tracked files for a regex and return matching lines as 'path:line: text'.

    Pattern is an extended regex. path_pattern optionally narrows the search to a git
    pathspec such as 'src/**/*.ts'. This runs `git grep`, so brace groups and globs behave
    the way they do on the command line. An empty result is a real answer — report it as
    "searched and found nothing", not as "does not exist".
    """
    global _repo_spent
    if _repo_spent >= REPO_BUDGET:
        return (f"Repo budget of {REPO_BUDGET // 1024}KB is spent — nothing was searched. "
                f"Answer with what you have and say which points stayed unverified.")
    args = ["grep", "-n", "-I", "-E", "--", pattern, *_pathspecs(path_pattern)]
    out, err = _git(*args, timeout=60)
    if err:
        return err
    hits = [ln for ln in (out or "").splitlines() if ln]
    if not hits:
        return (f"No matches for {pattern!r}"
                + (f" under {path_pattern!r}" if path_pattern else "")
                + ". The search ran and came back empty — report that as a search result, "
                  "not as proof the behaviour is absent.")
    head = hits[:GREP_LINES]
    text = "\n".join(head)
    _repo_spent += len(text.encode())
    note = "" if len(hits) <= GREP_LINES else \
        f"\n\n({len(hits)} matches, {GREP_LINES} shown — narrow the pattern to see the rest.)"
    return text + note


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
        # The budget gate must hold for EVERY backend. It once did not: the Brave path was
        # added later and checked nothing, so a stored brave key silently lifted the cap —
        # and this very test missed it by only ever configuring an ollama key.
        pathlib.Path(d, "keys.json").write_text(json.dumps({"ollama": "fake", "brave": "fake"}))
        out = web_search("anything")
        assert "budget" in out, "budget gate must hold with a brave key stored too"
        pathlib.Path(d, "keys.json").write_text(json.dumps({"ollama": "fake"}))
        _spent = 0

        os.environ.pop("PANEL_REPO", None)                   # no repo in scope
        for fn, arg in ((list_files, ""), (read_file, "x"), (grep_repo, "x")):
            assert "PANEL_REPO is unset" in fn(arg), f"{fn.__name__} must say so, not guess"

        # A real git repo: one tracked file, one untracked, one gitignored.
        repo = pathlib.Path(d, "repo")
        repo.mkdir()
        run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True)
        run("init", "-q")
        run("config", "user.email", "t@t"); run("config", "user.name", "t")
        pathlib.Path(repo, ".gitignore").write_text(".env\n")
        pathlib.Path(repo, "kept.md").write_text("alpha\nbeta {a,b} gamma\n")
        pathlib.Path(repo, ".env").write_text("SECRET=hunter2\n")
        pathlib.Path(repo, "untracked.md").write_text("SECRET=hunter2\n")
        run("add", ".gitignore", "kept.md"); run("commit", "-qm", "x")
        os.environ["PANEL_REPO"] = str(repo)

        assert "kept.md" in list_files(), "tracked file must be listed"
        assert ".env" not in list_files(), "gitignored file must be invisible"
        assert "untracked" not in list_files(), "untracked file must be invisible"

        assert "alpha" in read_file("kept.md"), "tracked file must be readable"
        # Assert the property, not the wording: git refuses an escaping path with a
        # different message than an untracked one, and both are fine as long as the
        # contents never come back.
        for hidden in (".env", "untracked.md", "../repo/.env", str(repo / ".env"),
                       "../../etc/passwd", "kept.md/../.env"):
            assert "hunter2" not in read_file(hidden), f"{hidden} leaked file contents"

        # The regression that withdrew these tools: pathlib.glob does not expand {a,b}.
        assert "kept.md:2" in grep_repo("beta"), "grep must find present text"
        assert "kept.md" in grep_repo("gamma", "*.{md,txt}"), "brace pathspec must work"
        assert "came back empty" in grep_repo("nowhere-at-all"), "empty must not read as absent"

        ns = {}
        exec(pathlib.Path(__file__).read_text(), ns)         # exactly how llm loads this
        exposed = sorted(n for n, v in ns.items() if callable(v) and not n.startswith("_"))
        assert exposed == ["grep_repo", "list_files", "read_file", "web_fetch",
                           "web_search"], f"unexpected tools exposed: {exposed}"
        print("panel_tools self-check: ok")
