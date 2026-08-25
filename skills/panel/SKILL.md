---
name: panel
description: Run an external multi-model panel review and reconcile the results. Triggers on "panel", "panel this", "second opinion", "ask the outside models", "cross-check this", or /panel — and on 「会诊」「外部会诊」「问问外面的模型」「交叉验证」「让它们评评」. The panel is five non-Claude models on ollama cloud; for Claude's own models (opus/sonnet/fable) use the consult skill instead.
argument-hint: [the question to review]
allowed-tools: Read, Grep, Glob, Bash
context: fork
---

Convene an external panel review on $ARGUMENTS.

The five panelists (all on ollama cloud, one OpenAI-compatible endpoint):
`deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax`

## Language

**Write the question package and the final summary in the language the user asked in.**
Chinese question → Chinese package, Chinese summary (立场矩阵 / 共识区 / 分歧区 / 独有洞察).
English question → English throughout. Never mix: one language end to end.

These instructions are in English so anyone can read and fork them. That has nothing to do
with what language you answer in — follow the user.

## 0. Is it worth it at all

**The test: if this decision turns out wrong, how expensive is the rework?** Expensive →
convene. Cheap → don't.

Never convene for: naming things, writing a utility function, or anything where the user
already has an answer and just wants agreement. That last one only manufactures a fake
consensus.

## 1. Build the question package

The panel cannot see this conversation and cannot see the codebase. **Everything they need
has to be handed over by hand.** Use Read/Grep to pull the real content, then assemble:

- Background and stack (one line)
- The goal and the hard constraints
- The relevant code **verbatim — paste it in full, never elide with `...`**
- Decisions, constraints and exact user quotes that were settled in conversation but never
  written to disk
- At most three specific questions

**Never cap the answer length in the package** — no "keep it brief", no "three sentences",
no "under 500 words". Capping the number of questions (three) keeps them focused; capping
the answer length just makes them cut the reasoning and hand back a bare verdict, and
**the reasoning is the whole point** — the adjudication in §3 turns on whose argument holds
up, not on whose conclusion sounds nicer. Tell them to take the space they need.

**Never state a preference** ("I'm leaning toward option A"). With a single reviewer,
naming your leaning provokes a useful rebuttal; with a panel it anchors all five at once
and makes a fake consensus real. To review an existing design, frame it neutrally: "Below
is one candidate. Evaluate its costs and the alternatives independently."

Write the package to `$D/q.md` with Write (`$D` comes from the next step).

## 2. Fan it out

```bash
export NO_PROXY='ollama.com'   # bypass a system proxy that can't reach ollama.com
[ -n "$OLLAMA_API_KEY" ] || { echo "OLLAMA_API_KEY not set — stopping"; exit 1; }
D=~/.claude/panel-runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$D/out" && echo "$D"
```

Once the package is written to `$D/q.md`:

```bash
cd "$D" && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'timeout 360 llm -m {} --key "$OLLAMA_API_KEY" -o reasoning_effort max < q.md > out/{}.md 2> out/{}.err || echo "PANELIST FAILED exit=$?" >> out/{}.err'
for f in out/*.err; do [ -s "$f" ] && { echo "== ${f}"; cat "$f"; }; done
wc -c out/*.md
```

All five run concurrently, so wall-clock is whatever the slowest survivor takes, and
`timeout 360` caps that at six minutes no matter what. **Give the Bash call a 420000
timeout** — 360s for the models plus overhead.

**Three settings are welded shut. Do not undo them:**

- **`timeout 360` per panelist, and the panel proceeds without the stragglers.** Without
  it one model hangs the whole review: the openai client's own default is **600 seconds**,
  so a single stuck call means ten minutes of nothing. 360 is not a guess — it is where
  the measured distribution has a clean break. Across 55 real calls, a 360s cap killed
  **both** runaway generations and **zero** legitimate answers (the slowest honest
  completion was 354s). At 300s it would have killed five good answers. Note the margin is
  thin: an occasional missing panelist is the accepted price, which is exactly why the
  summary must name absences instead of hiding them.

- **Never send `max_tokens`.** `llm` omits it by default (the request body was measured:
  only `messages`/`model`/`reasoning_effort`/`stream`), so each model stops when it is
  actually done. **Never impose an output cap on the panel** — the whole point is letting
  them finish the argument. Runaway generations do happen (twice in 55 calls, both
  `deepseek-flash`, both hitting the server's own 65536-token ceiling with
  `finish_reason: length` after 6–9 minutes), but the fix for those is the wall-clock
  timeout above, not a token cap that would truncate honest answers — legitimate ones have
  been measured as long as 17466 tokens.
- **`-o reasoning_effort max`.** The endpoint accepts `none`/`low`/`medium`/`high`/`max`
  (an invalid value errors, which proves the field is honored rather than ignored).
  Measured on one hard Raft question: `high` → 4406 chars of reasoning / 2688 of answer;
  `max` → 9667 / 4180. The unset default sits between them but is not stable. **A panel is
  only convened for high-stakes questions; there is no reason to economize here.**

Drop to `high` only when the question is easy and you're in a hurry. Never use
`low`/`none` — at that point you may as well not convene.

Read every `out/*.md` when it finishes. **If any `.err` is non-empty or any `.md` is zero
bytes, say plainly in the summary that that panelist was absent** — never imply all five
answered when they didn't. `PANELIST FAILED exit=124` means it hit the 360s cap; any other
exit code is a real error and the `.err` file says what it was.

**Four answers are still a panel — go ahead and reconcile them.** Never re-run a timed-out
panelist to "complete the set": it doubles the wall-clock for one more opinion, and the
user is waiting. Just name who is missing.

## 3. Reconcile (four fixed sections, none optional)

1. **Position matrix** — every issue × every model (agrees / disagrees / didn't mention)
2. **Consensus** — where three or more landed independently in the same place; mark it
   high-confidence
3. **Disagreements** — the actual point of contention and each side's reasoning, then your
   adjudication and the evidence for it
4. **Lone insights** — raised by exactly one model but holding up under scrutiny; **this is
   often the most valuable section**, so give it its own space

**Never decide by vote count.** These five share a great deal of training data and can be
confidently wrong together; the lone dissent is frequently the correct one. Weigh by
argument quality and by whether a claim can be falsified against code or a real test —
and where you can check it yourself by Reading the code, check it before adjudicating.

Close with: **your final recommendation + what must still be verified in practice + the
archive path `$D`**.

## 4. Optional second round: anonymized peer review (off by default)

Stage 2 from Karpathy's llm-council. **Off by default** — roughly 4–9× the tokens plus one
more serial wave of latency.

**When it earns its cost**: the five answers look equally plausible side by side; the
disagreement is about whose reasoning is stronger rather than about a fact; or the stakes
are high enough (architecture call, pre-launch security surface).

**Why strip the attributions**: models favor output that looks like their own house style,
so bylines introduce brand bias.

With round one done and `$D` still present:

```bash
cd "$D"
{ cat q.md
  echo; echo "---"
  echo "Below are five independent answers to the question above, with authorship removed. Assess each one's **argument quality** (not whether its position is popular), rank them and justify the ranking. If any of them raises a point none of the others did that holds up, call it out separately."
  set -- A B C D E
  for f in out/*.md; do echo; echo "### Answer $1"; echo; cat "$f"; shift; done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'timeout 360 llm -m {} --key "$OLLAMA_API_KEY" -o reasoning_effort max < r2.md > out2/{}.md 2> out2/{}.err || echo "PANELIST FAILED exit=$?" >> out2/{}.err'
for f in out2/*.err; do [ -s "$f" ] && { echo "== $f"; cat "$f"; }; done
wc -c out2/*.md
```

Write the round-two prompt in the user's language, same as everything else.

`out/` in alphabetical order = deepseek-flash / glm / kimi / minimax / nemotron, mapping to
A–E. **That mapping stays between you and the user — never put it in `r2.md`.**

Fold round two into the four sections above: an answer several panelists found holes in
gets downgraded even if its position was the majority one; a minority view several
panelists endorsed moves up alongside the consensus.

## Troubleshooting

```bash
# endpoint + key + model id, all three at once (should print one sentence)
NO_PROXY='ollama.com' llm -m glm --key "$OLLAMA_API_KEY" "Introduce yourself in one sentence."

llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # are the aliases registered
curl -s https://ollama.com/v1/models | jq -r '.data[].id'          # live catalog, for swapping models
llm logs -n 5                                                      # every past exchange, in local SQLite
```

- All five 401 → `$OLLAMA_API_KEY` wasn't picked up, or the key was rotated.
- All five `Connection error` → `NO_PROXY='ollama.com'` is missing.
- Swapping or adding a model: edit `extra-openai-models.yaml` in `llm`'s config directory
  (`dirname "$(llm logs path)"`), then update the model list in the commands above.
