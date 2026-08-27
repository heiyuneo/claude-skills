---
name: panel
description: Run an external multi-model panel review and reconcile the results. Triggers on "panel", "panel this", "second opinion", "ask the outside models", "cross-check this", or /panel — and on 「会诊」「外部会诊」「问问外面的模型」「交叉验证」「让它们评评」. The panel is five non-Claude models, each on its own configurable endpoint; for Claude's own models (opus/sonnet/fable) use the consult skill instead.
argument-hint: [the question to review]
allowed-tools: Read, Write, Grep, Glob, Bash
context: fork
---

Convene an external panel review on $ARGUMENTS.

The five panelists: `deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax`

Each carries its own endpoint, key alias and reasoning effort, configured outside this file
(`extra-openai-models.yaml` and `llm models options`). **Never pass `--key` on the command
line**: it overrides every `api_key_name` at once while leaving each `api_base` alone, so one
key reaches three providers and the two that did not issue it answer `401`.

**Write the package and the summary in the language the user asked in** — one language end
to end, never mixed.

## 0. When not to convene

Never convene when the user already has an answer and wants agreement. That manufactures a
fake consensus, which is worse than no panel at all.

## 1. Build the question package

The panel can search the web and read the repository (§2), but it **cannot see this
conversation**, and it will not navigate a codebase you know better. Hand over the
load-bearing material yourself — a panelist sent hunting for the central file spends its
budget navigating instead of thinking. Use Read/Grep to pull the real content, then assemble:

- Background and stack (one line)
- The goal and the hard constraints
- The relevant code **verbatim — paste it in full, never elide with `...`**
- Decisions, constraints and exact user quotes settled in conversation but never written down
- At most three specific questions

**Never cap the answer length in the package** — no "keep it brief", no "three sentences".
Capping questions keeps them focused; capping length makes them drop the reasoning, and the
reasoning is the whole point: §3 adjudicates on whose argument holds up.

**Always end the package with these requirements:**

> 1. List the key assumptions your answer rests on (at most five, most load-bearing first).
> 2. State what evidence would change your mind.
> 3. List what this package does not contain that you would have needed, and what you
>    assumed in its absence.
> 4. For every external fact you assert, mark whether you checked it with a tool (give the
>    source) or are asserting it from memory. An unmarked factual claim will be read as
>    unchecked.

**#3 is the only signal that does not pass through you** — when several panelists name the
same gap, that is a curation defect and it belongs in the summary.

**Never state a preference** ("I'm leaning toward option A"). With one reviewer, naming your
leaning provokes a rebuttal; with a panel it anchors all five at once.

**A preference you did not state can still be sitting in the material** — a pasted review
verdict, an adjudication table, a "we decided X". Handing those over verbatim is usually
right, so do not hide them; instead:

- Say so in one line: *"§N contains an internal review's verdict. It is reported so you can
  attack it, not so you can ratify it."*
- Ask the open question. Do not phrase it around the verdict's own framing ("is this order
  wrong?" makes the verdict the default answer).
- **Flag it for yourself, because §3 has to price it.**

**When the package forbids challenging a decision, that decision gets no evidence from this
run** — silence about it means nothing, and the summary should say so rather than read it as
endorsement.

Write the package to `$D/q.md` with Write (`$D` comes from the next step).

## 2. Fan it out

```bash
export NO_PROXY='ollama.com'   # bypass a system proxy that can't reach ollama.com
llm keys list 2>/dev/null | grep -q . || { echo "No API keys stored — run: llm keys set ollama"; exit 1; }
export TOOLS="$(dirname "$(llm logs path)")/panel_tools.py"
export PANEL_REPO="$(git rev-parse --show-toplevel 2>/dev/null)"   # repo the panel may read
for m in deepseek-flash nemotron glm kimi minimax; do          # effort lives per model, not here
  llm models options show "$m" 2>/dev/null | grep -q reasoning_effort || {
    echo "$m has no reasoning_effort default — the panel would silently run at the server's."
    echo "Fix once:  python3 \"$(dirname "$(llm logs path)")/panel-doctor.py\" --set-effort max"; exit 1; }
done
D=~/.claude/panel-runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$D/out" && echo "$D"
[ -n "$PANEL_REPO" ] && echo "repo in scope: $PANEL_REPO" || echo "no repo in scope — package is the panel's only source"
```

`PANEL_REPO` is captured here because the panelists run with their cwd inside the archive.
Empty → §1 curation is the only route to your code, and that belongs in the summary.

**Never add `-o reasoning_effort` back to the fan-out.** An explicit `-o` outranks every
stored default, which would make the whole per-model configuration unusable. The preflight
above is a hard gate rather than a warning because an unset effort does not error — it runs
at whatever the server picks and the answer looks completely normal.

**Now write `$D/baseline.md` — your own independent answer, in a few lines — before you
launch the fan-out.** It works mechanically, by existing on disk before any answer can anchor
you: a `baseline.md` older than the first file in `out/` is proof, one written afterwards is
only an assertion. Do not skip it because you feel unbiased.

**End it with a numbered list: the sharpest points you believe this question turns on, at
most five, one line each.** §3 turns each entry into a row of the position matrix whether or
not any panelist raised it.

Once `$D/q.md` and `$D/baseline.md` are both written:

```bash
cd "$D" && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=$1       # -n1 not -I{}: BSD -I caps the assembled command line,
      if [ "$m" = minimax ]; then     # and the fan-out then dies with no panelist called
        timeout 720 llm -m "$m" --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"
      else                          # keep "$TOOLS" quoted — it lives under Application Support
        timeout 720 llm -m "$m" --functions "$TOOLS" --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"
      fi || echo "PANELIST FAILED exit=$?" >> "out/$m.err"' _
for f in out/*.md; do                    # thresholds mirror check-run.sh — change both
  s=$(wc -c < "$f"); n=$(basename "$f" .md); e=$(cat "out/$n.err")
  if   [ "$s" -lt 200 ];  then echo "ABSENT     $n (${s}B) $e"
  elif [ "$s" -lt 3000 ]; then echo "UNUSABLE   $n (${s}B) $e"
  elif [ -n "$e" ];       then echo "TRUNCATED  $n (${s}B) $e"
  else                         echo "ok         $n (${s}B)"; fi
done
sqlite3 "$(llm logs path)" "select model||' finish='||coalesce(json_extract(response_json,'\$.finish_reason'),'null') from turns order by id desc limit 5;"
```

**Give the Bash call a 800000 timeout.**

`--functions` gives every panelist except minimax two web tools and three repo tools, the
latter scoped to `PANEL_REPO` and to what `git ls-files` reports. **Tool access removes the
excuse, not the risk** — §3 still adjudicates. What each tool does, why the repo three were
withdrawn once and rebuilt, and the self-check to run after editing them all live in
`panel_tools.py`'s module docstring.

**`--cl 60` is a fuse, not a throttle.** Hitting the chain limit kills the call outright
(exit 1, zero bytes), so it must sit above real usage. Measured: at the old `--cl 25` two
panelists burned every call navigating the source and were cut off mid-investigation, and a
repo-heavy question spends repo calls at roughly thirty times the rate of web searches. A
panelist that vanishes after a long silence is the first thing to check in the log.

**Four states, and all four matter:**

- **ABSENT** (under 200 bytes) catches the silent failure: exit 0, empty `.err`, one newline.
- **UNUSABLE** (200–3000 bytes) is a panelist that died on its first tool call, leaving *"let
  me go check a few facts first"* and nothing else. Measured: 294 B and 442 B in one run
  against a shortest-real-answer of 7620 B. **Counts exactly as ABSENT** for attendance, the
  re-run trigger and confidence — with one exception, in §3.4.
- **TRUNCATED** — `.err` non-empty (usually `exit=124`), **or the log says `finish=length`**,
  which the byte check cannot see at all because a runaway answer is *large*. It has content
  but probably no conclusion (nemotron's two kills each still held 22–25 KB of real answer):
  use its reasoning, never score its silence as "didn't mention", mark its row.
- **ok** — the only state you may treat as complete, and the bands are a first pass, not the
  verdict. Measured: a 3326-byte file passed as `ok` containing only a panelist narrating its
  own tool calls. **Open every file before you trust its label.**

**Two settings are welded shut:**

- **A per-panelist `timeout`, and the panel proceeds without stragglers.** Without it one
  model hangs the whole review. 720 is a correction rather than a measurement — re-derive it
  from `select model, duration_ms from turns` once enough tool-using panels have run.
- **Never send `max_tokens`.** Each model stops when it is done. Runaways happen, but
  `timeout` is the fix; a token cap truncates honest answers, which have run to 17466 tokens.

**Re-run only when the panel lost its majority**, counting ABSENT **and UNUSABLE** as missing.
1 missing → reconcile and move on. 2+ → re-run only those, once. 3+ still missing → don't
summarize; report and let the user decide. Two opinions is not a panel.

**`sleep 60` before the re-run, and retry stragglers one at a time.** Measured twice on glm:
the first attempt stalls and is killed locally, but the abandoned request still holds the
account's concurrency slot, so an immediate retry collides with the panelist's own corpse and
returns `429`. One failure, read as two.

## 3. Reconcile (five fixed sections, none optional)

Open `$D/baseline.md` now, before you read a single answer, and let the summary begin by
saying where the panel moved you and where it did not.

1. **Position matrix** — every issue × every model: agrees / disagrees / **considered and
   rejected** / didn't mention. The fourth state matters; a rejected-on-purpose position is
   evidence, not silence. Mark any TRUNCATED row so its gaps aren't read as positions.

   **Rows come from two sources: every issue the panel raised, *and* every entry on your
   `baseline.md` list — mark those `(source: baseline)`.** Rows are otherwise harvested from
   the answers, so a point all five missed has no row and never appears; with the second
   source it renders as **an entire row of "didn't mention"**, which is what a correlated
   blind spot looks like. Measured: five panelists, 155 repo calls between them, **0/5**
   noticed that one system verified signatures on the server and never on the client.

2. **Consensus** — where three or more landed in the same place, priced by independence:

   - **Check their assumption lists first.** Agreement plus heavily overlapping assumptions
     is convergence from a shared starting point — say "converged, possibly from the same
     premises", not "high confidence".
   - **Sort by what they agreed *with*.** Agreeing with a conclusion the package supplied is
     restatement, not corroboration — label it, even when unanimous. Agreement where they
     **contradict** the package is the most independent signal available. A 3/3 consensus can
     be worth less than a 3/3 dissent; printing both under one heading misleads.
   - **Two panelists are not interchangeable votes.** An answer rich in checked external
     facts is usually just kimi, the deepest tool user — thoroughness, not corroboration.
     minimax runs without tools, so it is the control: agreement with it means the package
     alone sufficed; a lone dissent from it asks whether the tools changed anyone's mind or
     only gave them more to cite.

3. **Disagreements** — the actual contention, each side's reasoning, then your adjudication
   and the evidence for it.

4. **Lone insights** — raised by exactly one model but holding up; often the most valuable
   section. **Harvest the wreckage too**: this is the one place UNUSABLE and TRUNCATED files
   are not treated as absent. Measured: a panelist that contributed 294 usable bytes supplied
   the only observation about a load-bearing sequencing error.

5. **Not covered, not verified** — dimensions the package never asked about, gaps panelists
   named under requirement #3, and every load-bearing claim you did **not** check. Without
   this section the four tidy headings above read as completeness.

   **Say where the matrix ends.** Its rows have exactly two sources, so anything neither you
   nor any panelist thought of is not merely unanswered but *unstatable* here. One sentence
   admitting that boundary; a reader who knows the shape of the hole can go looking.

**Never decide by vote count.** These five share a great deal of training data and can be
confidently wrong together; the lone dissent is frequently correct. Weigh by argument quality
and by whether a claim can be falsified against code or a test — and where you can check it
yourself, check it before adjudicating.

**Calibrate confidence to who showed up.** 5/5 → state conclusions plainly. 4/5 → hedge the
consensus. 3/5 → say explicitly that confidence is low and the consensus may be an artifact
of who answered. Writing a 4/5 result in a 5/5 voice is the most likely way this skill
misleads.

**A ceiling worth admitting:** you framed the question and you adjudicate it. Nothing above
removes that bias — the baseline and the assumption lists only make it visible. Say so on
questions with no external anchor, rather than implying the guards are sufficient.

### Stamping claims

**Mark every load-bearing claim that enters your recommendation** — not every sentence, only
what the recommendation rests on:

- `[verified-static <path:line or URL>]` — an artifact exists and says this.
- `[verified-live <command / query / log>]` — the state of the world was actually probed.
- `[unverified]`

Measured: of six "measured" claims fact-checked across two runs, **four were fabricated**.

**A static artifact cannot verify a claim about execution.** Anything asserting that
something *happened*, *is running*, *was deployed* is a claim about world state, and
`verified-static` does not support it — not as a judgement call but as a type error visible
in the line itself. Two legal moves: **write it down degraded** ("the recipe exists; whether
it ran is unknown") or go get live evidence.

**Degrading is a complete answer.** You are not obliged to probe production, and must not
acquire `verified-live` by running anything with side effects. Measured: two panelists once
reported a database "had been seeded" when the repo proved only that a seed script and a
deploy recipe existed — every path and line they cited was real, so a two-valued stamp had
nothing to object to.

### Delivering it

**Deliver the whole summary as the text of your answer, in full** — never a digest of itself
with the detail left in a file.

**Do not try to `Write` it to `$D/summary.md` yourself.** This skill runs in a fork, and a
subagent writing a file named `summary.md` is refused at the tool layer — *"Subagents should
return findings as text, not write report files."* That silently cost twelve runs their
summary. End your answer with this line and let the caller do it:

> Please write this summary verbatim to `$D/summary.md` — the fork cannot write it itself.
> 请把以上汇总全文原样写入 `$D/summary.md`（fork 无法自己落盘）。

Use whichever line matches the language of the run. **The caller must actually write it,
verbatim** — the archive is the only way anyone can later compare what the five said against
what the summary claims they said, which is the one check this design cannot perform on
itself.

End the summary with your final recommendation, what still needs verifying in practice, and
the archive path `$D`.

## 4. Second round: anonymized peer review

Stage 2 from Karpathy's llm-council. **Off by default**, but the decision is not yours to sit
on — it costs 4–9× the tokens and one more serial wave, and the user pays and waits.

**Before closing §3, compute the trigger. Any of these hits:**

- the consensus section is empty, or
- four or more agree but none argued against their own position, or
- the central disagreement cannot be falsified by code or a test.

**On a hit, print one line and stop for an answer:**

> Round 2 trigger hit: `<which one>`. Anonymized peer review costs about +4 minutes and
> 4–9× the tokens. Run it?

Bylines are stripped because models favour output in their own house style. The anonymity is
partial — you hold the mapping, and a model may recognise its own writing.

```bash
cd "$D"
{ cat q.md
  echo; echo "---"
  echo "Below are independent answers to the question above, with authorship removed. Assess each one's **argument quality** (not whether its position is popular), rank them and justify the ranking. If any of them raises a point none of the others did that holds up, call it out separately. Finally: if there is an important issue that *every* answer here missed, name it — you can see all of them at once, which none of their authors could."
  i=0
  for f in out/*.md; do
    [ "$(wc -c < "$f")" -lt 3000 ] && continue   # skip ABSENT and UNUSABLE alike
    i=$((i+1)); echo; echo "### Answer $i"; echo; cat "$f"
  done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=$1
      timeout 360 llm -m "$m" < r2.md > "out2/$m.md" 2> "out2/$m.err" \
        || echo "PANELIST FAILED exit=$?" >> "out2/$m.err"' _
grep -c "^### Answer" r2.md; wc -c out2/*.md
```

Absent panelists are skipped, so the numbering covers only real answers — **never let an
empty file become an empty "Answer N"**. Keep the number→model mapping out of `r2.md`, and
write the round-two prompt in the user's language.

Fold round two into the five sections: an answer several panelists found holes in gets
downgraded even if its position was the majority one; a minority view several endorsed moves
up alongside the consensus.

## Troubleshooting

**Anything failing before the answers come back → run the doctor.** It probes all five
concurrently and names the fix rather than the symptom: unstored keys, unset effort, a
missing `panel_tools.py`, a proxy that can't reach the gateway, rate limits, drifted model
names.

```bash
python3 "$(dirname "$(llm logs path)")/panel-doctor.py" --ping
```

`llm logs -n 5` shows past calls and every tool call.

`check-run.sh` ships beside this file and audits a finished run: which artifacts landed,
whether `baseline.md` predates the first answer, whether every baseline entry became a matrix
row, and attendance under the four-state banding. Run it after a panel, not instead of
reading the answers. Its path depends on how the skill was installed:

```bash
CHECK=$(find ~/.claude/skills ~/.claude/plugins/cache -name check-run.sh -path '*panel*' 2>/dev/null | head -1)
sh "$CHECK" [$D]
```

A run's full trail is `$D` (package, answers, `baseline.md`, `summary.md`) plus llm's SQLite
(durations, tokens, finish reasons, every tool call). Thresholds are re-derivable from it, so
add no bookkeeping beyond those two.
