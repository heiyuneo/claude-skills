---
name: panel
description: Run an external multi-model panel review and reconcile the results. Triggers on "panel", "panel this", "second opinion", "ask the outside models", "cross-check this", or /panel — and on 「会诊」「外部会诊」「问问外面的模型」「交叉验证」「让它们评评」. The panel is five non-Claude models, each on its own configurable endpoint; for Claude's own models (opus/sonnet/fable) use the consult skill instead.
argument-hint: [the question to review]
allowed-tools: Read, Write, Grep, Glob, Bash
context: fork
---

Convene an external panel review on $ARGUMENTS.

The five panelists: `deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax`

Each one carries its own endpoint and its own key alias in `extra-openai-models.yaml`, so
providers can be mixed freely — a model can sit on a vendor's own API while the rest go
through a gateway. **Never pass `--key` on the command line**: an explicit key outranks
every entry in that file and would silently force all five onto one provider.

## Language

**Write the question package and the final summary in the language the user asked in.**
Chinese question → Chinese package, Chinese summary (立场矩阵 / 共识区 / 分歧区 / 独有洞察).
English question → English throughout. Never mix: one language end to end.

## 0. When not to convene

Never convene when the user already has an answer and just wants agreement. That only
manufactures a fake consensus, which is worse than no panel at all.

## 1. Build the question package

The panel can read the repository (§2 gives them `list_files` / `read_file` / `grep_repo`),
but it **cannot see this conversation**, and it does not know which files matter. Hand over
everything anyway: the tools are for verifying and for finding what you missed, not a
substitute for curation. Use Read/Grep to pull the real content, then assemble:

- Background and stack (one line)
- The goal and the hard constraints
- The relevant code **verbatim — paste it in full, never elide with `...`**
- Decisions, constraints and exact user quotes that were settled in conversation but never
  written to disk
- At most three specific questions

**Never cap the answer length in the package** — no "keep it brief", no "three sentences".
Capping the number of questions keeps them focused; capping the answer length just makes
them cut the reasoning and hand back a bare verdict, and **the reasoning is the whole
point** — the adjudication in §3 turns on whose argument holds up, not on whose conclusion
sounds nicer.

**Always end the package with these two requirements:**

> 1. List the key assumptions your answer rests on (at most five, most load-bearing first).
> 2. State what evidence would change your mind.

This is the cheapest instrument that exists for detecting **shared** assumptions. All five
panelists read the same package, so their errors are correlated by construction; assumption
lists are what make that correlation visible in §3 instead of being scored as agreement.

**Never state a preference** ("I'm leaning toward option A"). With a single reviewer,
naming your leaning provokes a useful rebuttal; with a panel it anchors all five at once
and manufactures a consensus that isn't real.

**When the package forbids challenging a decision, that decision gets no evidence from
this run.** Reviewing an existing design means handing over the design and its rationale,
which anchors hard. If you also write "don't propose overturning X", then silence about X
means nothing — say so in the summary rather than reading it as endorsement.

Write the package to `$D/q.md` with Write (`$D` comes from the next step).

## 2. Fan it out

```bash
export NO_PROXY='ollama.com'   # bypass a system proxy that can't reach ollama.com
llm keys list 2>/dev/null | grep -q . || { echo "No API keys stored — run: llm keys set ollama"; exit 1; }
export PANEL_REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
export TOOLS="$(dirname "$(llm logs path)")/panel_tools.py"
D=~/.claude/panel-runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$D/out" && echo "$D"
```

Once the package is written to `$D/q.md`:

```bash
cd "$D" && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'timeout 540 llm -m {} -o reasoning_effort max --functions "$TOOLS" --cl 6 < q.md > out/{}.md 2> out/{}.err || echo "PANELIST FAILED exit=$?" >> out/{}.err'
for f in out/*.md; do
  s=$(wc -c < "$f"); n=$(basename "$f" .md); e=$(cat "out/$n.err")
  if   [ "$s" -lt 200 ]; then echo "ABSENT     $n (${s}B) $e"
  elif [ -n "$e" ];      then echo "TRUNCATED  $n (${s}B) $e"
  else                        echo "ok         $n (${s}B)"; fi
done
```

All five run concurrently, so wall-clock is whatever the slowest survivor takes, and
`timeout 540` caps that at nine minutes. **Give the Bash call a 600000 timeout.**

**The panel can check things.** `--functions` hands each panelist four read-only tools —
`list_files`, `read_file`, `grep_repo` over the repo, and `web_search` over the public web —
defined in `panel_tools.py`, which lives beside `extra-openai-models.yaml` in llm's config
directory. `--cl 6` caps the total tool rounds, shared across all four.

This exists because panelists that cannot check anything invent things instead: across two
real runs, six "measured" claims were fact-checked and **four were fabricated**, delivered
in exactly the same confident register as the true ones. The two tool families cover the two
fabrication classes — repo tools for claims about this codebase, `web_search` for claims
about the world (library versions, whether an API exists, what a cited source actually
says), which is where the earlier fabrications clustered. Repo access also routes around the
curator's blind spot: an allow-list chosen by the curator could only ever confirm what the
curator already thought was relevant, which is the one failure the tools exist to catch.

**Tool access does not make their claims true.** It removes the excuse, not the risk — a
model can still read one file and assert something about another. §3 still adjudicates.

The exposure boundary lives in `panel_tools.py`, not here: a deny-list (`external/`,
`docs/research/`, `.git/`, `node_modules/`, `target/`), a 256KB per-file limit, and a 256KB
total budget per panelist that **refuses rather than truncates** when exhausted — a model
that knows it was refused says so; one handed half a file reasons confidently about the
half it got. Set `PANEL_REPO_ROOT`; without it the tools disable themselves rather than
guessing at a root.

**Three states, and all three matter:**

- **ABSENT** (`.md` under 200 bytes) catches a silent failure: exit code 0, empty `.err`,
  and a `.md` containing one newline. Observed once, with a 16KB package — three of five
  came back that way on the first wave, `output_tokens` and `finish_reason` both null in
  `llm logs`. Every package under 9KB has been fine. A byte check is the only thing that
  catches it; the shortest legitimate answer in a real panel was 7620 bytes, so there is
  no risk of a false kill.
- **TRUNCATED** (real output, but `.err` is non-empty) is usually `exit=124` — killed at
  the 540s cap mid-stream. **It has content but probably no conclusion.** Use its
  reasoning, never score its silence on an issue as "didn't mention", and label it in the
  matrix.
- **ok** is the only state you may treat as a complete answer.

**Two settings are welded shut. Do not undo them:**

- **A per-panelist `timeout`, and the panel proceeds without the stragglers.** Without it
  one model hangs the whole review — the openai client's own default is 600 seconds. The
  previous cap of 360 was measured: across 55 tool-free calls it killed both runaway
  generations and zero legitimate answers (slowest honest completion: 354s). **540 is not
  measured** — it is 360 plus room for six tool rounds, and it needs re-deriving from the
  logs once enough tool-using panels have run. Until then, expect more TRUNCATED than
  before, and name every absence.
- **Never send `max_tokens`.** Each model stops when it is actually done. Runaways do
  happen (twice in 55 calls, both `deepseek-flash`, both hitting the endpoint's own 65536
  ceiling with `finish_reason: length`), but the wall-clock timeout is the fix for those —
  a token cap would truncate honest answers, which have run as long as 17466 tokens.

**Re-run only when the panel actually lost its majority:**

- **1 absent → reconcile the rest and move on.** Never re-run to "complete the set": it
  doubles the wall-clock for one more opinion while the user waits.
- **2 or more absent → re-run just those, once.** Measured: one such re-run cost 3 minutes
  and recovered the two most substantive answers of that session. Note that re-sending an
  unchanged package does not always help — one panelist returned empty both times.
- **3 or more still absent → don't summarize.** Report what happened and let the user
  decide. Two opinions is not a panel.

## 3. Reconcile (four fixed sections, none optional)

**Before reading any answer, write `$D/baseline.md`: your own independent answer to the
question, in a few lines.** Do this first, always. It is not a self-assessment ritual —
it works mechanically, by existing on disk before the first strong opinion can anchor you,
and by leaving the user an auditable record of how far the final verdict moved from your
prior. Do not skip it because you feel unbiased.

Then:

1. **Position matrix** — every issue × every model (agrees / disagrees / **considered and
   rejected** / didn't mention). The fourth state matters: "didn't mention" otherwise
   swallows four different things, and a rejected-on-purpose position is evidence, not
   silence. Mark any TRUNCATED panelist's row so its gaps aren't read as positions.
2. **Consensus** — where three or more landed in the same place. **Check their assumption
   lists (§1) before labelling it high-confidence.** If they agree *and* their assumptions
   overlap heavily, that is convergence from a shared starting point — say "converged, and
   possibly from the same premises", not "high confidence". All five read the same package;
   nothing in this design makes them independent.
3. **Disagreements** — the actual contention, each side's reasoning, then your adjudication
   and the evidence for it.
4. **Lone insights** — raised by exactly one model but holding up under scrutiny; **often
   the most valuable section**, and short answers land here as often as long ones.

**Never decide by vote count.** These five share a great deal of training data and can be
confidently wrong together; the lone dissent is frequently the correct one. Weigh by
argument quality and by whether a claim can be falsified against code or a real test —
and where you can check it yourself by Reading the code, check it before adjudicating.

**Calibrate confidence to who showed up.** 5/5 → state conclusions plainly. 4/5 → hedge
the consensus claims. 3/5 → say explicitly that confidence is low and the consensus may be
an artifact of who happened to answer. Writing a 4/5 result in a 5/5 voice is the most
likely way this skill misleads.

**A ceiling worth admitting:** you framed the question in §1 and you adjudicate it here.
Nothing above removes that bias — the baseline file and the assumption lists only make it
visible. On questions with no external anchor to check against, "argument quality" partly
means "agrees with my prior". Say so when it applies rather than implying the guards are
sufficient.

Close with: **your final recommendation + what must still be verified in practice + the
archive path `$D`**.

## 4. Second round: anonymized peer review

Stage 2 from Karpathy's llm-council. **Off by default**, but the decision is not yours to
sit on — it costs roughly 4–9× the tokens and one more serial wave, and the user is the one
paying and waiting.

**Before closing §3, compute the trigger. Any of these hits:**

- the consensus section is empty, or
- four or more agree but none of them argued against their own position, or
- the central disagreement cannot be falsified by code or a test.

**On a hit, you must print one line and stop for an answer** — never decide for yourself
whether it is worth it:

> Round 2 trigger hit: `<which one>`. Anonymized peer review costs about +4 minutes and
> 4–9× the tokens. Run it?

**Why strip the attributions**: models favor output that looks like their own house style,
so bylines introduce brand bias. The anonymity is partial and you should not overstate it —
you hold the mapping, and a model may well recognize its own writing.

With round one done and `$D` still present:

```bash
cd "$D"
{ cat q.md
  echo; echo "---"
  echo "Below are independent answers to the question above, with authorship removed. Assess each one's **argument quality** (not whether its position is popular), rank them and justify the ranking. If any of them raises a point none of the others did that holds up, call it out separately."
  i=0
  for f in out/*.md; do
    [ "$(wc -c < "$f")" -lt 200 ] && continue
    i=$((i+1)); echo; echo "### Answer $i"; echo; cat "$f"
  done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -I{} sh -c 'timeout 360 llm -m {} -o reasoning_effort max < r2.md > out2/{}.md 2> out2/{}.err || echo "PANELIST FAILED exit=$?" >> out2/{}.err'
grep -c "^### Answer" r2.md; wc -c out2/*.md
```

Absent panelists are skipped, so the numbering covers only real answers — **never let an
empty file become an empty "Answer N"**. Keep the number→model mapping out of `r2.md`.
Write the round-two prompt in the user's language.

Fold round two into the four sections: an answer several panelists found holes in gets
downgraded even if its position was the majority one; a minority view several panelists
endorsed moves up alongside the consensus.

## Troubleshooting

```bash
# endpoint + key + model id, all three at once (should print one sentence)
NO_PROXY='ollama.com' llm -m glm "Introduce yourself in one sentence."

llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"   # are the aliases registered
curl -s https://ollama.com/v1/models | jq -r '.data[].id'          # live catalog, for swapping models
llm logs -n 5                                                      # every past exchange, in local SQLite
```

- All five 401 → `$OLLAMA_API_KEY` wasn't picked up, or the key was rotated.
- All five `Connection error` → `NO_PROXY='ollama.com'` is missing.
- Swapping or adding a model: edit `extra-openai-models.yaml` in `llm`'s config directory
  (`dirname "$(llm logs path)"`), then update the model list in the commands above.

Every call is logged to `llm`'s SQLite (`llm logs path`) with model, duration, tokens and
finish reason, and every run leaves its package and answers in `$D`. That is the whole
audit trail — timings, failure rates and the 360s threshold can all be re-derived from it,
so don't add bookkeeping on top.
