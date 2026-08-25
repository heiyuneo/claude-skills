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
reasoning defeats the point. Budget your tool timeout accordingly (the skill uses 900s).

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

## What the panel can read

Each panelist gets three read-only tools — `list_files`, `read_file`, `grep_repo` — over the
repo you invoke it from. They exist because a panelist that cannot check anything invents
instead: across two real runs, six "measured" claims were fact-checked and **four were
fabricated**, in the same confident tone as the true ones.

The boundary is in `setup/panel_tools.py`, and it is worth understanding before you point
this at a private repo:

| Guard | Value |
|---|---|
| Excluded paths | `external/`, `docs/research/`, `.git/`, `node_modules/`, `target/` |
| Per-file limit | 256KB |
| Total per panelist | 256KB, and it **refuses** rather than truncating when spent |
| Tool rounds | 6 (`--cl 6`) |
| Root | `PANEL_REPO_ROOT`; unset means the tools disable themselves |

Edit the `DENY` tuple for your own repo — that list is the whole exposure decision. Note
that a deny-list is deliberate: an allow-list would be chosen by the same curator whose
blind spot the tools exist to route around, so it could only ever confirm what the curator
already thought was relevant.

Every tool call is recorded in llm's SQLite (`tool_calls`, `tool_results`), so you can audit
afterwards exactly which files each model pulled.

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
