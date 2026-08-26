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

Two more that exist because of specific failures, and are worth knowing as a *reader* of a
summary:

- **Every load-bearing claim carries one of three stamps** — `verified-static` (an artifact
  says so), `verified-live` (the world was actually probed), or `unverified` — and **a
  static artifact may not verify a claim about execution**. Two panelists once reported a
  database "had been seeded" when the repo proved only that a seed script and a deploy
  recipe existed; every path and line they cited was real, so a two-valued stamp had nothing
  to object to. The three-valued one makes that a visible type error rather than a question
  someone has to remember to ask.
- **Claude writes its own answer before the fan-out, as a short numbered list, and every
  entry becomes a row of the matrix** — marked `(source: baseline)`, whether or not any
  panelist raised it. Matrix rows are otherwise harvested from the answers, so a point all
  five missed would have no row and would simply never appear. Measured: five panelists,
  three with repo access and 155 repo lookups between them, and **none** noticed that one
  system verified signatures on the server but never on the client. With this rule it shows
  up as an entire row of "didn't mention", which is what a shared blind spot looks like.

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

# fetch the setup files: model aliases, search backends, the tools, and the doctor
CFG="$(dirname "$(llm logs path)")"; mkdir -p "$CFG"
for f in extra-openai-models.yaml panel_tools.py panel-doctor.py panel-search.json; do
  curl -fsSL "https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/$f" -o "$CFG/$f"
done

# store the key (prompts for it — nothing lands in your shell history)
llm keys set ollama

# set each panelist's reasoning effort, then see what's still missing
python3 "$CFG/panel-doctor.py" --set-effort max
```

The doctor prints one row per panelist — endpoint, key alias, whether that key is stored,
its effort — and the exact commands for anything missing. **The shipped lineup spans three
providers**, so it will tell you about two keys you have not stored yet; the next section is
how to either store them or point those two panelists somewhere you already have a key.

`llm` writes it to `keys.json` beside that config file, mode 0600. **Don't put it in an
environment variable instead** — env vars get inherited by every process you launch, and
because every OpenAI-compatible model falls back to the *same* `OPENAI_API_KEY`, they
can't express per-model keys at all (see [Configure your own lineup](#configure-your-own-lineup)).

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

## Configure your own lineup

A panelist is three independent choices — **which provider**, **which key**, **how hard it
thinks** — and none of them are baked into the skill. The skill only ever calls five
aliases: `deepseek-flash`, `nemotron`, `glm`, `kimi`, `minimax`. Where each alias points is
entirely yours.

Run the doctor any time to see the current wiring and what it needs:

```bash
python3 "$(dirname "$(llm logs path)")/panel-doctor.py" --ping
```

```
alias           model              endpoint          key alias  stored  effort  reachable
deepseek-flash  deepseek-v4-flash  api.deepseek.com  deepseek   yes     max     ok
glm             glm-5.3            open.bigmodel.cn  zhipu      NO      unset   skipped
...
```

### Provider and key

Every entry in `extra-openai-models.yaml` carries its own `api_base` and `api_key_name`, so
a panelist can be routed to any OpenAI-compatible endpoint — a vendor's own API, a gateway,
a local server, a private deployment — while the rest stay where they are. Three lines move
one model:

```yaml
- model_id: deepseek-flash                   # what the skill calls — never change this
  model_name: deepseek-v4-flash              # that provider's own name for it
  api_base: "https://api.deepseek.com/v1"    # instead of the gateway
  api_key_name: deepseek                     # instead of: ollama
  reasoning: true                            # required, or effort can't be set at all
```

Then store that key once: `llm keys set deepseek`.

**Don't want an account with one of these vendors?** Point that panelist at a provider you
already use. Everything on Ollama Cloud, one key, is a perfectly good panel — you lose a
model version or two, not the design. The five aliases are five *seats*, not five vendors.

### How hard each one thinks

Effort is stored per model in llm's own config, not passed by the skill:

```bash
llm models options set glm reasoning_effort max
llm models options show glm
python3 "$(dirname "$(llm logs path)")/panel-doctor.py" --set-effort max   # all five at once
```

**Tiers differ by provider.** Ollama Cloud accepts `none/low/medium/high/max`; DeepSeek's
own API also takes `minimal` and `xhigh`. Both honour `max`. A provider that rejects the
field outright fails the whole call, so test one model by hand after repointing it.

⚠️ **An unset effort is the one failure here that stays quiet.** It doesn't error — the model
just runs at whatever the server picks, and the answer looks completely normal. The skill
refuses to start rather than let that happen, and `--set-effort max` clears it in one
command. This is also why the skill no longer hard-codes `-o reasoning_effort max`: an
explicit flag outranks every stored default, which would make all of the above unusable.

### Which search engine answers

`web_search` walks a list of backends in order and returns the first one that finds
something. The list lives in `panel-search.json` beside the model table, and it is a table
you edit for exactly the same reason the model table is:

```json
{
  "name": "brave",                       // what shows up as "(index: brave)" in the answer
  "key": "brave",                        // which stored llm key to use
  "url": "https://api.search.brave.com/res/v1/web/search?extra_snippets=true&q={q}",
  "header": { "X-Subscription-Token": "{key}" },
  "results": "web.results",              // dotted path to the array of results
  "title": "title", "link": "url",       // which field is the title, which is the URL
  "content": ["description", "extra_snippets"]   // fields to join into the excerpt
}
```

POST-style APIs work too — add `"method": "POST"` and a `"body"` object; `{q}` and `{key}`
are substituted in both. Any provider that returns a JSON array of results with a title, a
URL and some text can be mapped in about eight lines.

**A backend with no stored key is skipped silently**, so you can leave entries in the file
as templates and activate one by storing its key. The shipped file has Brave first and
Ollama second; `panel-doctor.py` prints the active order so you can see which one actually
answered.

Why more than one: **one index finding nothing is not evidence of absence.** When every
configured backend comes back empty the tool says exactly that, so a panelist can never turn
silence into "it does not exist". That is the entire reason a second index is worth a key —
not that any index is more trustworthy than another.

### Two things worth knowing

- **Never add `--key` to the fan-out command.** It overrides every `api_key_name` at once
  while leaving each `api_base` alone, so one key gets presented to several providers and
  the ones that did not issue it answer `401`. The shipped commands deliberately don't use it.
- **Going direct is also a diagnostic.** If a panelist is unreliable through a gateway and
  stable on the vendor's own endpoint, the gateway was the problem, not the model.

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
max reasoning effort. The skill deliberately sends **no `max_tokens`** — a panel exists to get the full argument,
and truncating the reasoning defeats the point. Reasoning effort is *not* sent by the skill
either; it comes from each model's own stored default, so you can raise one panelist and
lower another (see [Configure your own lineup](#configure-your-own-lineup)). With repo and web tools in the loop each panelist is capped at 720s and the whole fan-out at
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

⚠️ **The four files in `setup/` do not ride along with the plugin** — `llm` owns that config
directory, not Claude Code. After an update that touches them, re-run the `curl` loop from
step 2, then `panel-doctor.py` to confirm. A missing `panel_tools.py` fails **all five**
panelists at once, since `--functions` cannot load.

## License

MIT
