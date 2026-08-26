# heiyu-claude-skills

Claude Code skills. Currently one: **panel — an external multi-model panel review.**

[中文说明 →](./README.zh.md)

## panel — five outside models, called in for a second opinion

Normally when you ask Claude Code something, exactly one model answers. Some decisions
deserve better than that: should this module be split out, does this concurrent write have
a race I can't see, is this PR safe to ship.

Install this and you say "panel this" — it packages your question *along with the relevant
code* and fans it out to five **non-Claude** models
(DeepSeek, Nemotron, GLM, Kimi, MiniMax), all in parallel, all at max reasoning effort.
Claude then takes the five opinions back and reconciles them into five parts:

| Section | What goes in it |
|---|---|
| **Position matrix** | Every issue × every model — agrees / disagrees / **considered and rejected** / didn't mention |
| **Consensus** | Where three or more landed in the same place, labelled by how independent that agreement actually is |
| **Disagreements** | The actual arguments on each side, plus an adjudication and the evidence for it |
| **Lone insights** | Points only one model raised that survive scrutiny — often the most valuable part |
| **Not covered, not verified** | Dimensions the question never asked about, and every load-bearing claim that went unchecked |

Four rules the skill enforces on itself. They exist because the failure mode here is not a
bad answer — it is **five answers that agree and are wrong together**, which reads as
confirmation and stamps your own prior as verified:

- **It never decides by vote count.** These five share a lot of training data and can be
  confidently wrong together; a lone dissent is often the correct one. Claims get weighed
  by argument quality and by whether they can be checked against code or a real test.
- **It never tells the panel your preferred answer.** Stating a leaning anchors all five
  models at once and manufactures a consensus that isn't real.
- **Consensus is graded by what it agreed *with*.** Agreeing with a conclusion your own
  question package supplied is restatement, not corroboration. Agreement on a point where
  they **contradict** the package is the strongest signal this design can produce — nothing
  was pushing them there. The two never print under one heading.
- **Confidence follows attendance.** 5/5 states conclusions plainly, 4/5 hedges, 3/5 has to
  say out loud that the consensus may be an artifact of who happened to answer.

## When to use it

Use it when **being wrong is expensive to undo**: architecture calls, a security surface
before launch, a technology choice you'll live with for a year.

Don't use it for naming things, writing a utility function, or anything where you already
have an answer and just want agreement. That last one only buys you a fake consensus.

## Install (two minutes, three steps)

### 1. Get an Ollama key first

Go to <https://ollama.com/settings/keys>, sign in, hit **Create key**, copy it.

⚠️ **Bring your own.** Ollama Cloud is metered and bills to whoever's key it is. Don't
borrow someone else's.

### 2. Paste this whole block into a terminal

```bash
# install the llm CLI
uv tool install llm                 # no uv? use: brew install llm

# fetch the two setup files: model aliases, and the read-only repo tools
CFG="$(dirname "$(llm logs path)")"; mkdir -p "$CFG"
for f in extra-openai-models.yaml panel_tools.py; do
  curl -fsSL "https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/$f" -o "$CFG/$f"
done

# store the key (prompts for it — nothing lands in your shell history)
llm keys set ollama
```

`llm` writes it to `keys.json` beside that config file, mode 0600. **Don't put it in an
environment variable instead** — env vars get inherited by every process you launch, and
because every OpenAI-compatible model falls back to the *same* `OPENAI_API_KEY`, they
can't express per-model keys at all (see [Mixing providers](#mixing-providers)).

Check it right away. One sentence back means key, endpoint and model are all correct:

```bash
NO_PROXY='ollama.com' llm -m glm "Introduce yourself in one sentence."
```

### 3. Install the plugin in Claude Code

```
/plugin marketplace add heiyuneo/claude-skills
/plugin install panel@heiyu-claude-skills
```

Restart Claude Code and say "panel this: ...".

## Mixing providers

Nothing ties the panel to one vendor. Every entry in `extra-openai-models.yaml` carries its
own `api_base` and its own `api_key_name`, so any panelist can be routed to any
OpenAI-compatible endpoint — a vendor's own API, a gateway, a local server, a private
deployment — while the rest stay where they are.

Store the extra key once:

```bash
llm keys set deepseek
```

Then point that one model at it:

```yaml
- model_id: deepseek-flash
  model_name: deepseek-v4-flash              # vendor's own name for it
  api_base: "https://api.deepseek.com/v1"    # instead of the gateway
  api_key_name: deepseek                     # instead of: ollama
  reasoning: true
```

The `model_id` is the alias the skill uses, so changing where it points doesn't touch the
skill at all.

Two things worth knowing before you do this:

- **Never add `--key` to the fan-out command.** An explicit key outranks every `api_key_name`
  in the file and silently forces all five models onto one provider. The shipped commands
  deliberately don't use it.
- **Effort tiers differ by provider.** Ollama Cloud accepts
  `none/low/medium/high/max`; DeepSeek's own API accepts `none/minimal/low/medium/high/xhigh/max`.
  Both honour `max`, which is what the skill sends, but a provider that rejects the field
  outright will fail the whole call — test one model by hand before wiring it in.

Going direct is also a diagnostic: if a panelist is unreliable through a gateway and stable
on the vendor's own endpoint, the gateway was the problem, not the model.

The same one-line move adds a second search index rather than a second model — store a
`brave` key and `web_search` starts querying Brave before Ollama's index. Optional; see
[What the panel can check](#what-the-panel-can-check).

```bash
llm keys set brave    # https://api-dashboard.search.brave.com
```

## Three things that will bite you

1. **No key ships in this repo, and none ever should.** Everyone uses their own key on
   their own account.

2. **`NO_PROXY='ollama.com'`** — every command in the skill carries it. Harmless on a
   machine with no proxy, so leave it in. Drop it behind a proxy that can't reach
   `ollama.com` and every call dies with `Connection error`.

3. **Model names drift.** `setup/extra-openai-models.yaml` pins specific versions
   (`glm-5.3`, `kimi-k3`, …). When you get a "model not found", check what's
   live and edit the file:

   ```bash
   curl -s https://ollama.com/v1/models | jq -r '.data[].id'
   ```

## Cost and latency

Five models run concurrently, so wall-clock is whatever the slowest one takes: roughly
12 seconds for a short question, but **minutes** for a real one with code pasted in at
max reasoning effort. The skill deliberately sends **no `max_tokens`** and always uses
`reasoning_effort: max` — a panel exists to get the full argument, and truncating the
reasoning defeats the point. With repo and web tools in the loop each panelist is capped at 720s and the whole fan-out at
800s — the round trips are billed to the same clock, and three overruns at the old 540s cap
still had 22–25 KB of real answer in them when they were killed.

## Troubleshooting

| Symptom | Cause |
|---|---|
| All five return 401 | Key not stored via `llm keys set`, or rotated |
| All five `Connection error` | Missing `NO_PROXY='ollama.com'` |
| All five fail instantly | `panel_tools.py` missing from llm's config dir — `--functions` can't load |
| One panelist vanishes after a long silence | It hit the `--cl` chain limit; the fuse kills the call outright |
| `model not found` | Model name drifted — see #3 above |

```bash
llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # are the aliases registered
llm keys list                                                     # which keys are stored
llm logs -n 5                                                     # every past exchange, in local SQLite
```

## What the panel can check

Each panelist gets five tools, and no others.

**The outside world** — `web_search`, `web_fetch`. They exist because a panelist who cannot
check anything invents instead: of six "measured" claims fact-checked across two runs,
**four were fabricated**, in the same confident tone as the true ones — and all four were
world facts (a library's version, whether an API exists, what a cited source says). Search
finds the source; fetch reads the primary page rather than reasoning from snippets about it.

`web_search` will query **two independent indexes** if you let it: store a `brave` key and it
tries Brave first, falling back to Ollama's index when Brave errors or comes back empty, with
each result labelled by the index that answered. That is not a claim about bias — it is
coverage. One index finding nothing is not evidence of absence, and when both come back empty
the tool says exactly that, so silence is never read as "does not exist". Skip the key and
search simply uses Ollama. Either way `web_fetch` stays on Ollama, since Brave returns
snippets and no page body.

**Your repository** — `list_files`, `read_file`, `grep_repo`, scoped to the repo Claude
convened the panel from. Without them the question package is the only thing that ever
reaches the panel, which makes one person's curation the entire world five models get to see
— and that person is also the one adjudicating at the end.

These three shipped once, were withdrawn, and are back **rebuilt rather than restored**,
because the two failures that withdrew them have different lessons:

- A deny-list meant to hide secrets was walked around by a `.worktrees/` copy of the tree.
  The fix is not a better pattern list — it is **not having one**. Visibility is now defined
  positively by `git ls-files`, so anything untracked simply does not exist for these tools:
  `.env`, keystores, build output and stray worktree copies are out of reach by construction,
  and there is no rule to maintain or get wrong.
- A search built on `pathlib.glob` spent 85 seconds answering "No matches" for text that was
  plainly present, because `pathlib` does not expand `{a,b}`. **That is the one that must
  never come back**: a tool reporting a false absence is worse than no tool, since the model
  then asserts the absence in an "I checked" register and your verification step becomes the
  thing manufacturing the hallucination. The base is `git grep`, brace groups are expanded
  before the pathspec is handed over, every empty result says the search *ran* and came back
  empty, and `setup/panel_tools.py` carries a self-check covering exactly that regression.

Each panelist may pull 192KB of web content and 512KB of repo content before the tools start
refusing, and a refusal tells the model to answer with what it has and say which points
stayed unverified.

Everything that reaches the panel — the question package, all five raw answers, Claude's own
answer written *before* the fan-out, and the final summary — is archived under
`~/.claude/panel-runs/`, so you can always compare what the five actually said against what
the summary claims they said. To audit one run:

```bash
CHECK=$(find ~/.claude/skills ~/.claude/plugins/cache -name check-run.sh -path '*panel*' 2>/dev/null | head -1)
sh "$CHECK"
```

## Known temperament, per panelist

Worth knowing before you misdiagnose one:

| Alias | Behaviour |
|---|---|
| `kimi` | The reliable leg, and the deepest tool user of the five. A `grep_repo` claim it made about this repo checked out to the exact file and line, and it labelled its own answers `checked` and `second-hand, not chased` without being asked |
| `deepseek-flash` | Occasionally runs away into the endpoint's own token ceiling; the per-panelist timeout catches it |
| `nemotron` | Doesn't fail, overruns — both times it was killed the file still held 22–25 KB of real answer |
| `minimax` | **Runs with tools off.** It died on full-size packages three times, but "breaks on tool calls" is not the diagnosis — single searches succeed at every effort tier in seconds. What reproduces is **non-convergence**: asked to check four facts it re-ran near-identical queries instead of using what it already had. Unencumbered it has twice produced the panel's longest answer, and it is the only panelist reasoning purely from the package — the natural control against the tool-using four |
| `glm` | Its first request occasionally stalls at zero bytes, and retrying *immediately* then hits `429` — the abandoned request still holds the account's concurrency slot. The skill waits before re-running a straggler |

## Updating

```
/plugin marketplace update heiyu-claude-skills
/plugin update panel
```

⚠️ **The two files in `setup/` do not ride along with the plugin** — `llm` owns that config
directory, not Claude Code. After an update that touches them, re-run the `curl` loop from
step 2. A missing `panel_tools.py` fails **all five** panelists at once, since `--functions`
cannot load.

## License

MIT
