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
Claude then takes the five opinions back and reconciles them into four parts:

| Section | What goes in it |
|---|---|
| **Position matrix** | Every issue × every model — agrees / disagrees / didn't mention |
| **Consensus** | Where three or more independently landed in the same place |
| **Disagreements** | The actual arguments on each side, plus an adjudication |
| **Lone insights** | Points only one model raised that survive scrutiny — often the most valuable part |

Two rules the skill enforces on itself:

- **It never decides by vote count.** These five share a lot of training data and can be
  confidently wrong together; a lone dissent is often the correct one. Claims get weighed
  by argument quality and by whether they can be checked against code or a real test.
- **It never tells the panel your preferred answer.** Stating a leaning anchors all five
  models at once and manufactures a consensus that isn't real.

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

## Three things that will bite you

1. **No key ships in this repo, and none ever should.** Everyone uses their own key on
   their own account.

2. **`NO_PROXY='ollama.com'`** — every command in the skill carries it. Harmless on a
   machine with no proxy, so leave it in. Drop it behind a proxy that can't reach
   `ollama.com` and every call dies with `Connection error`.

3. **Model names drift.** `setup/extra-openai-models.yaml` pins specific versions
   (`glm-5.3`, `kimi-k2.7-code`, …). When you get a "model not found", check what's
   live and edit the file:

   ```bash
   curl -s https://ollama.com/v1/models | jq -r '.data[].id'
   ```

## Cost and latency

Five models run concurrently, so wall-clock is whatever the slowest one takes: roughly
12 seconds for a short question, but **minutes** for a real one with code pasted in at
max reasoning effort. The skill deliberately sends **no `max_tokens`** and always uses
`reasoning_effort: max` — a panel exists to get the full argument, and truncating the
reasoning defeats the point. With repo and web tools in the loop each panelist is capped at 540s, and the whole fan-out at 600s.

## Troubleshooting

| Symptom | Cause |
|---|---|
| All five return 401 | Key not picked up, or rotated |
| All five `Connection error` | Missing `NO_PROXY='ollama.com'` |
| `model not found` | Model name drifted — see #3 above |

```bash
llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # are the aliases registered
llm logs -n 5                                                     # every past exchange, in local SQLite
```

## What the panel can check

Each panelist gets two tools, `web_search` and `web_fetch`, and nothing else. They exist
because a panelist who cannot check anything invents instead: of six "measured" claims
fact-checked across two runs, **four were fabricated**, in the same confident tone as the
true ones — and all four were world facts (a library's version, whether an API exists, what
a cited source says). Search finds the source; fetch reads the primary page rather than
reasoning from snippets about it.

`web_search` reuses the `ollama` key you already stored, so there is nothing extra to sign
up for. Without it, both tools return a plain "unavailable" instead of failing. Each
panelist may pull 192KB of web content before the tools start refusing.

**The panel cannot read your repository.** Tools that did (`list_files`, `read_file`,
`grep_repo`) shipped once and were withdrawn after two measured runs: a deny-list defeated
by a git worktree copy of excluded files, a search that spent 85 seconds and answered "No
matches" for text that was present (`pathlib.glob` does not expand `{a,b}`), and zero usable
answers out of ten attempts. `setup/panel_tools.py` states the conditions for reinstating
them. A verification tool that lies is worse than none: it stamps a hallucination "checked".

So what reaches the panel is exactly what Claude puts in the question package — you can read
every one of them afterwards under `~/.claude/panel-runs/`.

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
