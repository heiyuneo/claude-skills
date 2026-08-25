"""Read-only repo access for panel members, passed to `llm --functions`.

Why this exists: the panelists otherwise cannot verify anything. Across two real panel
runs, six "measured" claims were fact-checked and four were fabricated — models with no
way to check invent, and the invention arrives in the same confident tone as fact.

Exposure model: the curator no longer decides file-by-file what leaves the machine, so
the boundary is drawn here instead — a deny-list, a byte budget, and a refusal (never a
truncation) when the budget runs out. Set PANEL_REPO_ROOT to the repo being reviewed;
without it the tools stay disabled rather than defaulting to somewhere surprising.
"""

import os
import re
import subprocess
from pathlib import Path

DENY = ("external/", "docs/research/", ".git/", "node_modules/", "target/")
MAX_READ = 256 * 1024      # any single file in a normal repo fits whole
BUDGET = 256 * 1024        # the real gate: total bytes one panelist may pull
GREP_HITS = 60

_spent = 0


def _root():
    r = os.environ.get("PANEL_REPO_ROOT")
    return Path(r).resolve() if r else None


def _resolve(path: str):
    """Return (resolved_path, error). Blocks escapes and denied prefixes."""
    root = _root()
    if not root:
        return None, "PANEL_REPO_ROOT is not set; repo access is disabled."
    p = (root / path).resolve()
    if not (p == root or root in p.parents):
        return None, f"Refused: {path} is outside the repository."
    rel = p.relative_to(root).as_posix()
    if any(rel.startswith(d) for d in DENY):
        return None, f"Refused: {rel} is in an excluded area ({', '.join(DENY)})."
    return p, None


def list_files(pattern: str = "**/*") -> str:
    """List repository files matching a glob pattern, e.g. 'apps/*/src/**/*.ts'.

    Use this to discover what exists before reading. Paths are relative to the repo root.
    """
    root = _root()
    if not root:
        return "PANEL_REPO_ROOT is not set; repo access is disabled."
    out = []
    for p in sorted(root.glob(pattern)):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(rel.startswith(d) for d in DENY):
            continue
        out.append(f"{rel} ({p.stat().st_size // 1024}KB)")
        if len(out) >= 200:
            out.append("... (truncated at 200 entries; narrow the pattern)")
            break
    return "\n".join(out) or f"No files match {pattern}."


def read_file(path: str) -> str:
    """Read one repository file in full, given its path relative to the repo root.

    Refuses rather than truncates when the byte budget is exhausted, so you always know
    whether you are looking at a complete file.
    """
    global _spent
    p, err = _resolve(path)
    if err:
        return err
    if not p.is_file():
        return f"Not found: {path}"
    size = p.stat().st_size
    if size > MAX_READ:
        return (f"Refused: {path} is {size // 1024}KB, over the {MAX_READ // 1024}KB "
                f"per-file limit. Use grep_repo to locate the relevant part instead.")
    left = BUDGET - _spent
    if size > left:
        return (f"Refused: {path} is {size // 1024}KB but only {left // 1024}KB of the "
                f"read budget remains. Nothing was read — pick a smaller file, or use "
                f"grep_repo. Say so in your answer if this limits your conclusion.")
    _spent += size
    return p.read_text(encoding="utf-8", errors="replace")


def grep_repo(pattern: str, path_glob: str = "**/*") -> str:
    """Search repository file contents for a regular expression.

    Returns matching lines as 'path:line: text'. Use this to locate code before reading a
    whole file, and to check whether something exists at all.
    """
    root = _root()
    if not root:
        return "PANEL_REPO_ROOT is not set; repo access is disabled."
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return f"Bad regular expression: {e}"
    hits = []
    for p in sorted(root.glob(path_glob)):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(rel.startswith(d) for d in DENY):
            continue
        try:
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:200]}")
                    if len(hits) >= GREP_HITS:
                        hits.append(f"... (stopped at {GREP_HITS} matches; narrow the pattern)")
                        return "\n".join(hits)
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(hits) or f"No matches for {pattern}."


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        (root / "src/a.ts").write_text("export const x = 1;\n")
        (root / "external").mkdir()
        (root / "external/secret.md").write_text("unreleased\n")
        (root / "big.txt").write_text("x" * (300 * 1024))
        os.environ["PANEL_REPO_ROOT"] = str(root)

        assert "export const x" in read_file("src/a.ts")
        assert "excluded area" in read_file("external/secret.md"), "deny-list must hold"
        assert "outside the repository" in read_file("../../etc/passwd"), "no escapes"
        assert "per-file limit" in read_file("big.txt"), "oversize must refuse"
        assert "src/a.ts" in list_files("**/*.ts")
        assert "external" not in list_files("**/*.md")
        assert "src/a.ts:1:" in grep_repo("export const")
        assert "No matches" in grep_repo("zzzz-not-present")

        _spent = BUDGET - 10                       # budget nearly gone
        out = read_file("src/a.ts")
        assert "read budget remains" in out, "must refuse, never truncate"
        assert "Nothing was read" in out
        print("panel_tools self-check: ok")
