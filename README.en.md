# heiyu-claude-skills

Claude Code skills. Currently one: **panel — an external multi-model panel review.**

[中文说明 →](./README.md)

## panel — five outside models, called in for a second opinion

Normally when you ask Claude Code something, exactly one model answers. Some decisions
deserve better than that: should this module be split out, does this concurrent write have
a race I can't see, is this PR safe to ship.

Install this and you say "panel this" — it packages your question *along with the relevant
code* and fans it out to five **non-Claude** models on [Ollama Cloud](https://ollama.com)
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

Replace `paste-your-key-here` on the last line with the key from step 1, then run the lot:

```bash
# install the llm CLI
uv tool install llm                 # no uv? use: brew install llm

# fetch the model aliases (tells llm what the five models are called and where to find them)
mkdir -p "$(dirname "$(llm logs path)")"
curl -fsSL https://raw.githubusercontent.com/heiyuneo/claude-skills/main/setup/extra-openai-models.yaml \
  -o "$(dirname "$(llm logs path)")/extra-openai-models.yaml"

# store the key
echo 'export OLLAMA_API_KEY=paste-your-key-here' >> ~/.zshenv && chmod 600 ~/.zshenv
source ~/.zshenv
```

⚠️ **The key goes in `.zshenv`, not `.zshrc`.** Claude Code spawns a fresh non-interactive
shell for every command, and non-interactive zsh only reads `.zshenv`. Put it in `.zshrc`
and the check below will pass when you type it yourself, but the skill will bail with
`OLLAMA_API_KEY 未设置` the moment it runs — a genuinely annoying half hour to debug.

Check it right away. One sentence back means key, endpoint and model are all correct:

```bash
NO_PROXY='ollama.com' llm -m glm --key "$OLLAMA_API_KEY" "Introduce yourself in one sentence."
```

### 3. Install the plugin in Claude Code

```
/plugin marketplace add heiyuneo/claude-skills
/plugin install panel@heiyu-claude-skills
```

Restart Claude Code and say "panel this: ...".

## Three things that will bite you

1. **No key ships in this repo, and none ever should.** Everyone uses their own key on
   their own account.

2. **`NO_PROXY='ollama.com'`** — every command in the skill carries it. Harmless on a
   machine with no proxy, so leave it in. Drop it behind a proxy that can't reach
   `ollama.com` and every call dies with `Connection error`.

3. **Model names drift.** `setup/extra-openai-models.yaml` pins specific versions
   (`glm-5.2`, `kimi-k2.7-code`, …). When you get a "model not found", check what's
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

## Updating

```
/plugin marketplace update heiyu-claude-skills
/plugin update panel
```

## License

MIT
