---
name: panel
description: Run an external multi-model panel review and reconcile the results. Triggers on "panel", "panel this", "second opinion", "ask the outside models", "cross-check this", or /panel — and on 「会诊」「外部会诊」「问问外面的模型」「交叉验证」「让它们评评」. The panel is five non-Claude models, each on its own configurable endpoint; for Claude's own models (opus/sonnet/fable) use the consult skill instead.
argument-hint: [the question to review]
allowed-tools: Read, Write, Grep, Glob, Bash
context: fork
---

Convene an external panel review on $ARGUMENTS.

Five panelists — `deepseek-flash` · `nemotron` · `glm` · `kimi` · `minimax` — each with its
own endpoint, key alias and reasoning effort, all configured outside this file. `NOTES.md`
beside this one holds the measurements behind every rule here; read a section of it when you
are about to change that thing, or when its symptom appears.

**Write the package and the summary in the language the user asked in** — one language end
to end, never mixed.

## 0. When to convene

Convene on genuinely open questions where being wrong is expensive to undo. A panel summoned
to agree only manufactures consensus, which is worse than no panel at all.

## 1. Build the question package

The panel can search the web and read the repository, but it **cannot see this conversation**
and will not navigate a codebase you know better. Hand over the load-bearing material
yourself. Use Read/Grep to pull the real content, then assemble:

- Background and stack (one line)
- The goal and the hard constraints
- The relevant code **verbatim — paste it in full, never elide with `...`**
- Decisions, constraints and exact user quotes settled in conversation but never written down
- At most three specific questions

**Ask for full reasoning at whatever length it takes.** Capping the question count keeps them
focused; capping answer length deletes exactly what §3 adjudicates on.

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

**Write the package leaning-free**: your job is to provoke attack, not agreement, and a
stated preference anchors all five at once.

**A preference you did not state can still be sitting in the material** — a pasted review
verdict, an adjudication table, a "we decided X". Handing those over verbatim is usually
right, so instead of hiding them:

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
**Check the line it echoes.** Empty is loud — the tools say there is no repo. Pointing at the
*wrong* repo is silent: it resolves from your cwd, so reviewing a project you are not
currently sitting in hands five models somebody else's code. Set it explicitly when they
differ. Either way, say in the summary which repo was in scope.

**Now write `$D/baseline.md` — your own independent answer, in a few lines — before you
launch the fan-out.** It works mechanically: a `baseline.md` older than the first file in
`out/` is proof it predates any anchoring, one written afterwards is only an assertion.

**End it with a numbered list: the sharpest points you believe this question turns on, at
most five, one line each.** §3 turns each entry into a row of the position matrix whether or
not any panelist raised it.

Once `$D/q.md` and `$D/baseline.md` are both written:

```bash
cd "$D" && date +%s > .fanout_started   # the instant baseline.md must predate
printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=\$1      # escaped on purpose: a bare positional is substituted, fences included
      if [ "$m" = minimax ]; then    # -n1 not -I{}: BSD -I caps the line, fan-out dies uncalled
        timeout 720 llm -m "$m" --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"     # no max_tokens: it truncates honest answers
      else                           # "$TOOLS" quoted: the path contains a space
        timeout 720 llm -m "$m" --functions "$TOOLS" --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"     # --cl is a fuse: too low = narration only
      fi || echo "PANELIST FAILED exit=$?" >> "out/$m.err"' _
for f in out/*.md; do                    # thresholds mirror check-run.sh — see NOTES.md#thresholds
  s=$(wc -c < "$f"); n=$(basename "$f" .md); e=$(cat "out/$n.err")
  if   [ "$s" -lt 200 ];  then echo "ABSENT     $n (${s}B) $e"
  elif [ "$s" -lt 3000 ]; then echo "UNUSABLE   $n (${s}B) $e"
  elif [ -n "$e" ];       then echo "TRUNCATED  $n (${s}B) $e"
  else                         echo "ok         $n (${s}B)"; fi
done
sqlite3 "$(llm logs path)" "select model||' finish='||coalesce(json_extract(response_json,'\$.finish_reason'),'null') from turns order by id desc limit 5;"
```

**Run this block in the background** (`run_in_background: true`) **and then wait for it to
finish before you do anything else.** A foreground Bash call is capped at 600 s — shorter
than one panelist's own `timeout 720` — so running it in the foreground gets killed
mid-block with the answers on disk but the triage never executed.

**Backgrounding without waiting is worse than the timeout it fixes**: launching and then
ending your turn abandons the run entirely — measured, on the first attempt at this very
instruction. The fan-out and the triage loop are one background call on purpose, so its
completion carries the four-state output. Nothing after this point is yours to start until
that output is in front of you.

**Every flag in that block was set by a failure — change none of them without reading
`NOTES.md#fan-out` first.** That covers the four knobs you will reach for when a run goes
badly: adding `max_tokens`, lowering `--cl`, putting `-o reasoning_effort` back, and passing
`--key`. Each of them makes the run *look* fine while breaking it.

`--functions` gives every panelist except minimax two web tools and three repo tools, the
latter scoped to `PANEL_REPO` and to what `git ls-files` reports. **Tool access removes the
excuse, not the risk** — §3 still adjudicates. What each tool does, and the self-check to run
after editing them, lives in `panel_tools.py`'s module docstring.

**Four states, and all four matter:**

- **ABSENT** (under 200 bytes) — exit 0, empty `.err`, one newline. The silent failure.
- **UNUSABLE** (200–3000 bytes) — died on its first tool call, leaving a preamble and no
  reasoning. **Counts exactly as ABSENT** for attendance, the re-run trigger and confidence
  — with one exception, in §3.4.
- **TRUNCATED** — `.err` non-empty, **or the log says `finish=length`**, which the byte check
  cannot see because a runaway answer is *large*. Has content but probably no conclusion: use
  its reasoning, never score its silence as "didn't mention", mark its row.
- **ok** — the only state you may treat as complete, and the bands are a first pass, not the
  verdict. **Open every file before you trust its label**; one has passed as `ok` containing
  only a panelist narrating its own tool calls.

**Re-run only when the panel lost its majority**, counting ABSENT **and UNUSABLE** as missing.
1 missing → reconcile and move on. 2+ → re-run only those, once. 3+ still missing → don't
summarize; report and let the user decide. Two opinions is not a panel.

**`sleep 60` before any re-run, and retry stragglers one at a time.** A panelist killed
locally may still hold its provider's concurrency slot, so an immediate retry collides with
its own corpse and fails for a different reason than the first attempt did.

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

   **Every cell that is not "didn't mention" carries a verbatim fragment of that model's own
   answer, written `model«…»`** — copied, not paraphrased, long enough to be unique (a dozen
   characters or so). `check-run.sh` greps each fragment back into `out/<model>.md` and fails
   the run on any that isn't there. The reader only ever reads the summary, and until this
   check existed the summary layer's own misquote rate was the one number this design never
   measured — the panelist layer's was measured at 4/6 fabricated. **A cell you cannot quote
   is a cell you inferred: write "didn't mention" instead.** For a rejected-on-purpose
   position, quote the rejection.

2. **Consensus** — where three or more landed in the same place, priced by independence:

   - **Check their assumption lists first.** Agreement plus heavily overlapping assumptions
     is convergence from a shared starting point — say "converged, possibly from the same
     premises", not "high confidence".
   - **Agreeing with a conclusion the package supplied is restatement, not corroboration** —
     label it as such, even when unanimous. Agreement where they **contradict** the package
     is the most independent signal available. A 3/3 consensus can be worth less than a 3/3
     dissent; printing both under one heading misleads.
   - **Two panelists are not interchangeable votes.** An answer rich in checked external
     facts is usually just kimi, the deepest tool user — thoroughness, not corroboration.
     minimax runs without tools, so it is the control: agreement with it means the package
     alone sufficed; a lone dissent from it asks whether the tools changed anyone's mind or
     only gave them more to cite.

3. **Disagreements** — the actual contention, each side's reasoning, then your adjudication
   and the evidence for it.

4. **Lone insights** — raised by exactly one model but holding up; often the most valuable
   section. **Harvest the wreckage too**: this is the one place UNUSABLE and TRUNCATED files
   are not treated as absent — a 294-byte fragment has been the only source of a real finding.

5. **Not covered, not verified** — dimensions the package never asked about, gaps panelists
   named under requirement #3, and every load-bearing claim you did **not** check. Without
   this section the four tidy headings above read as completeness.

   **Say where the matrix ends.** Its rows have exactly two sources, so anything neither you
   nor any panelist thought of is not merely unanswered but *unstatable* here. One sentence
   admitting that boundary; a reader who knows the shape of the hole can go looking.

**A panelist saying it checked something is not the same as it having found something.**
Tool access is visible in the answer's confidence, not in its accuracy — verify the citations
that carry your recommendation, however checked they sound.

**Weigh by argument quality and by whether a claim can be falsified against code or a test —
never by head-count.** These five share a great deal of training data and can be confidently
wrong together; the lone dissent is frequently correct. Where you can check a claim yourself,
check it before adjudicating.

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
- `[verified-live <command / query / log>]` — the state of the world was actually probed,
  read-only.
- `[unverified]`

Measured: of six "measured" claims fact-checked across two runs, **four were fabricated**.

**A static artifact cannot verify a claim about execution.** Anything asserting that
something *happened*, *is running*, *was deployed* is a claim about world state, and
`verified-static` does not support it — not as a judgement call but as a type error visible
in the line itself. Two legal moves: **write it down degraded** ("the recipe exists; whether
it ran is unknown") or go get live evidence. **Degrading is a complete answer** — you are
never obliged to probe production, and **you must not acquire `verified-live` by running
anything with side effects.** Read-only probes only; a stamp is never worth a mutation.

### Delivering it

**Deliver the whole summary as the text of your answer, in full** — never a digest of itself
with the detail left in a file.

**Do not try to `Write` it to `$D/summary.md` yourself.** A subagent writing a file by that
name is refused at the tool layer, and renaming around the guard is not the fix. End your
answer with this line and let the caller do it:

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
    [ "$(wc -c < "$f")" -lt 3000 ] && continue   # never let an empty file become an "Answer N"
    i=$((i+1)); echo; echo "### Answer $i"; echo; cat "$f"
  done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=\$1      # escaped, same reason as the first fan-out
      timeout 360 llm -m "$m" < r2.md > "out2/$m.md" 2> "out2/$m.err" \
        || echo "PANELIST FAILED exit=$?" >> "out2/$m.err"' _
grep -c "^### Answer" r2.md; wc -c out2/*.md
```

Keep the number→model mapping out of `r2.md`, and write the round-two prompt in the user's
language.

Fold round two into the five sections: an answer several panelists found holes in gets
downgraded even if its position was the majority one; a minority view several endorsed moves
up alongside the consensus.

## Troubleshooting

**Anything failing before the answers come back → run the doctor.** It probes all five
concurrently and names the fix rather than the symptom: unstored keys, unset effort, a
missing `panel_tools.py`, a proxy that can't reach the gateway, rate limits, drifted model
names. Symptoms it cannot explain are in `NOTES.md#per-panelist`.

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
sh "$CHECK" "$D"     # omit "$D" to audit the most recent run
```

A run's full trail is `$D` (package, answers, `baseline.md`, `summary.md`) plus llm's SQLite
(durations, tokens, finish reasons, every tool call). Add no bookkeeping beyond those two.
