#!/usr/bin/env python3
"""Show and fix how the five panelists are wired: provider, key, effort, reachability.

The panel is deliberately five *aliases*, not five vendors. Each one carries its own
endpoint and its own key in extra-openai-models.yaml, and its own reasoning effort in llm's
own per-model defaults — so any panelist can be moved to any OpenAI-compatible provider
without touching the skill. That freedom is worthless if nobody can see the current wiring,
which is what this does.

It exists because the shipped lineup spans three providers while the install flow stores one
key: following the README got you three panelists and two silent 401s, and a panel that
quietly runs at 3/5 reads exactly like a panel that ran at 5/5.

    python3 panel-doctor.py                 # report
    python3 panel-doctor.py --ping          # report, and actually call each model
    python3 panel-doctor.py --set-effort max            # all five
    python3 panel-doctor.py --set-effort xhigh --only glm

No dependencies: the yaml here is a flat list of scalars, parsed as such rather than
pulling in PyYAML for eight keys.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

FIELDS = ("model_id", "model_name", "api_base", "api_key_name")


def _cfg_dir() -> pathlib.Path:
    out = subprocess.run(["llm", "logs", "path"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("llm CLI not found. Install it first:  uv tool install llm")
    return pathlib.Path(out.stdout.strip()).parent


def _models(path: pathlib.Path):
    """Parse the flat `- model_id: x` list. Returns [{field: value}, ...] in file order."""
    if not path.exists():
        sys.exit(f"{path} is missing. Re-run the curl step from the README.")
    entries, cur = [], None
    for line in path.read_text().splitlines():
        if re.match(r"\s*#", line) or not line.strip():
            continue
        m = re.match(r"\s*-?\s*(\w+):\s*\"?([^\"#]*?)\"?\s*$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "model_id":
            cur = {"model_id": val}
            entries.append(cur)
        elif cur is not None and key in FIELDS:
            cur[key] = val
    return entries


def _backends(cfg: pathlib.Path):
    """The search backends, in the order web_search will try them."""
    import json as _json
    f = cfg / "panel-search.json"
    try:
        e = _json.loads(f.read_text())
        return e if isinstance(e, list) and e else []
    except (OSError, ValueError):
        return [{"name": "brave", "key": "brave"}, {"name": "ollama", "key": "ollama"}]


def _stored_keys():
    out = subprocess.run(["llm", "keys", "list"], capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines() if l.strip()}


def _effort(alias):
    out = subprocess.run(["llm", "models", "options", "show", alias],
                         capture_output=True, text=True)
    m = re.search(r"reasoning_effort:\s*(\S+)", out.stdout)
    return m.group(1) if m else None


def _ping(alias):
    env = {**os.environ, "NO_PROXY": "ollama.com"}
    out = subprocess.run(["llm", "-m", alias, "Reply with one word: ok"],
                         capture_output=True, text=True, timeout=120, env=env)
    if out.returncode == 0 and out.stdout.strip():
        return "ok", ""
    err = (out.stderr or "").strip().replace("\n", " ")
    m = re.search(r"Error code: (\d+)", err)
    return ("HTTP " + m.group(1) if m else "failed"), err[:90]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ping", action="store_true", help="actually call each model")
    ap.add_argument("--set-effort", metavar="TIER",
                    help="store this reasoning_effort as the default for the panelists")
    ap.add_argument("--only", metavar="ALIAS", help="limit --set-effort to one alias")
    args = ap.parse_args()

    cfg = _cfg_dir()
    models = _models(cfg / "extra-openai-models.yaml")

    if args.set_effort:
        targets = [m for m in models if not args.only or m["model_id"] == args.only]
        if not targets:
            sys.exit(f"No panelist called {args.only!r} in extra-openai-models.yaml")
        for m in targets:
            subprocess.run(["llm", "models", "options", "set", m["model_id"],
                            "reasoning_effort", args.set_effort], check=False)
        print()

    keys = _stored_keys()
    tools_ok = (cfg / "panel_tools.py").exists()

    rows, missing_keys, missing_effort = [], set(), []
    for m in models:
        alias = m["model_id"]
        kname = m.get("api_key_name", "?")
        have = kname in keys
        if not have:
            missing_keys.add(kname)
        eff = _effort(alias)
        if not eff:
            missing_effort.append(alias)
        host = re.sub(r"^https?://", "", m.get("api_base", "?")).split("/")[0]
        reach, detail = ("", "")
        if args.ping:
            reach, detail = _ping(alias) if have else ("skipped", "no key")
        rows.append((alias, m.get("model_name", "?"), host, kname,
                     "yes" if have else "NO", eff or "unset", reach, detail))

    w = [max(len(str(r[i])) for r in rows + [("alias", "model", "endpoint", "key alias",
                                              "stored", "effort", "reachable", "")])
         for i in range(7)]
    head = ("alias", "model", "endpoint", "key alias", "stored", "effort", "reachable")
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(head)).rstrip())
    print("  ".join("-" * w[i] for i in range(7 if args.ping else 6)))
    for r in rows:
        print("  ".join(str(r[i]).ljust(w[i]) for i in range(7 if args.ping else 6)).rstrip())
        if r[7]:
            print(" " * (w[0] + 2) + "└─ " + r[7])

    print()
    backends, unconfigured = _backends(cfg), []
    active = []
    for b in backends:
        (active if b.get("key") in keys else unconfigured).append(
            f"{b.get('name','?')}({b.get('key','?')})")
    print("web search : " + (" → ".join(active) if active
                             else "NONE CONFIGURED — no backend has a stored key"))
    if unconfigured:
        print("             " + ", ".join(unconfigured)
              + "  ← listed but no key stored, silently skipped")
    print("repo tools : " + ("panel_tools.py present" if tools_ok
                             else "panel_tools.py MISSING — all five panelists will fail"))

    todo = []
    for k in sorted(missing_keys):
        todo.append(f"llm keys set {k}"
                    + {"ollama": "        # https://ollama.com/settings/keys",
                       "deepseek": "      # https://platform.deepseek.com",
                       "zhipu": "         # https://open.bigmodel.cn"}.get(k, ""))
    if not any(b.get("key") in keys for b in backends):
        todo.append("llm keys set ollama        # no search backend has a key — panelists "
                    "would have to answer from memory")
    if missing_effort:
        todo.append("python3 panel-doctor.py --set-effort max"
                    f"   # unset on: {', '.join(missing_effort)}")
    if not tools_ok:
        todo.append("re-run the curl step from the README (panel_tools.py is missing)")

    if todo:
        print("\nto fix:")
        for t in todo:
            print("  " + t)
        print("\nDon't want an account for one of these? Point that panelist somewhere you\n"
              "already have a key — edit its three lines in\n"
              f"  {cfg / 'extra-openai-models.yaml'}\n"
              "    api_base:     the provider's OpenAI-compatible URL\n"
              "    api_key_name: an alias you have stored\n"
              "    model_name:   that provider's own name for the model\n"
              "The model_id is what the skill calls, so repointing it changes nothing else.")
    else:
        print("\nall five wired, keys stored, effort set.")


if __name__ == "__main__":
    main()
