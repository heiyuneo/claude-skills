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
through a gateway. **Never pass `--key` on the command line**: it overrides `api_key_name`
for every model at once while leaving each `api_base` alone, so one key gets presented to
three different providers and the two that did not issue it answer `401`. The models stay
five distinct models — what breaks is authentication, not the lineup. Store one key per
alias with `llm keys set <alias>`; an environment variable cannot express per-model keys,
because every OpenAI-compatible model falls back to the same `OPENAI_API_KEY`.

## Language

**Write the question package and the final summary in the language the user asked in.**
Chinese question → Chinese package, Chinese summary (立场矩阵 / 共识区 / 分歧区 / 独有洞察).
English question → English throughout. Never mix: one language end to end.

## 0. When not to convene

Never convene when the user already has an answer and just wants agreement. That only
manufactures a fake consensus, which is worse than no panel at all.

## 1. Build the question package

The panel can search the web (§2), but it **cannot see this conversation and cannot read
the repo**. Everything from either has to be handed over by hand. Use Read/Grep to pull the
real content, then assemble:

- Background and stack (one line)
- The goal and the hard constraints
- The relevant code **verbatim — paste it in full, never elide with `...`**
- Decisions, constraints and exact user quotes that were settled in conversation but never
  written to disk
- At most three specific questions

**Never cap the answer length in the package** — no "keep it brief", no "three sentences".
Capping questions keeps them focused; capping length makes them drop the reasoning, and
**the reasoning is the whole point**: §3 adjudicates on whose argument holds up.

**Always end the package with these requirements:**

> 1. List the key assumptions your answer rests on (at most five, most load-bearing first).
> 2. State what evidence would change your mind.
> 3. List what this package does not contain that you would have needed, and what you
>    assumed in its absence.
> 4. For every external fact you assert, mark whether you checked it with a tool (give the
>    source) or are asserting it from memory. An unmarked factual claim will be read as
>    unchecked.

#4 mirrors the `[verified]` duty §3 puts on you. It is one line and it costs nothing, and
the rate it guards against is the measured one: of six "measured" claims fact-checked across
two no-tool runs, four were fabricated. Panelists who mark their own claims hand you a
ready-made verification worklist instead of an undifferentiated wall of assertions.

All five read the same package, so their errors are correlated by construction. #1 and #2
make that correlation visible in §3 instead of scoring it as agreement. **#3 is the only
signal you get about your own curation** — the package is a black box that reports no
errors, so five independent reports of what was missing is the one channel that does not
pass through the curator. When several name the same gap, that is a curation defect, and it
belongs in the summary.

**Never state a preference** ("I'm leaning toward option A"). With a single reviewer,
naming your leaning provokes a useful rebuttal; with a panel it anchors all five at once
and manufactures a consensus that isn't real.

**A preference you did not state can still be sitting in the material.** The rule above
governs your sentences; it does not govern a pasted document that already announces a
winner — a review verdict, an adjudication table, a "we decided X after considering Y".
Handing those over verbatim is often correct (they are the real state of the work), so the
fix is not to hide them:

- Say so in the package, in one line: *"§N contains an internal review's verdict. It is
  reported so you can attack it, not so you can ratify it."*
- Do not phrase a question around the verdict's own framing ("is this order wrong?" makes
  the verdict the default answer). Ask the open question and let the verdict be material.
- **Flag it for yourself, because §3 has to price it**: agreement with a verdict the package
  supplied is worth close to nothing, while a point where several panelists **contradict**
  the supplied verdict is the highest-independence signal a panel can produce.

**When the package forbids challenging a decision, that decision gets no evidence from
this run.** Reviewing an existing design means handing over the design and its rationale,
which anchors hard. If you also write "don't propose overturning X", then silence about X
means nothing — say so in the summary rather than reading it as endorsement.

Write the package to `$D/q.md` with Write (`$D` comes from the next step).

## 2. Fan it out

```bash
export NO_PROXY='ollama.com'   # bypass a system proxy that can't reach ollama.com
llm keys list 2>/dev/null | grep -q . || { echo "No API keys stored — run: llm keys set ollama"; exit 1; }
export TOOLS="$(dirname "$(llm logs path)")/panel_tools.py"
export PANEL_REPO="$(git rev-parse --show-toplevel 2>/dev/null)"   # repo the panel may read
D=~/.claude/panel-runs/$(date +%Y%m%d-%H%M%S)
mkdir -p "$D/out" && echo "$D"
[ -n "$PANEL_REPO" ] && echo "repo in scope: $PANEL_REPO" || echo "no repo in scope — package is the panel's only source"
```

**`PANEL_REPO` must be captured here, before the `cd "$D"` below.** The panelists run with
their working directory inside the archive, so without this variable the repo tools have
nothing to point at and will say so instead of guessing. If the panel is convened somewhere
that is not a git repository the variable is empty, the repo tools report that plainly, and
§1 curation is again the only route to your code — which is worth saying in the summary.

**Now write `$D/baseline.md` — your own independent answer to the question, in a few lines —
and write it before you launch the fan-out.** It belongs here rather than in §3 because it
has nothing to do with the answers, and putting it here is the only way it can be *checked*:
a `baseline.md` older than the first file in `out/` is proof it was not written under the
influence of a strong opinion, and a `baseline.md` written afterwards is just an assertion
that it was. That auditability is the whole mechanism — the file works by existing on disk
before the first answer can anchor you, and by leaving the user a record of how far the final
verdict moved from your prior. Do not skip it because you feel unbiased.

Once `$D/q.md` and `$D/baseline.md` are both written:

```bash
cd "$D" && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=$1
      if [ "$m" = minimax ]; then                 # tools off for minimax only — see below
        timeout 720 llm -m "$m" -o reasoning_effort max --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"
      else
        timeout 720 llm -m "$m" -o reasoning_effort max --functions "$TOOLS" --cl 60 \
          < q.md > "out/$m.md" 2> "out/$m.err"
      fi || echo "PANELIST FAILED exit=$?" >> "out/$m.err"' _
for f in out/*.md; do
  s=$(wc -c < "$f"); n=$(basename "$f" .md); e=$(cat "out/$n.err")
  if   [ "$s" -lt 200 ];  then echo "ABSENT     $n (${s}B) $e"
  elif [ "$s" -lt 3000 ]; then echo "UNUSABLE   $n (${s}B) $e"
  elif [ -n "$e" ];       then echo "TRUNCATED  $n (${s}B) $e"
  else                         echo "ok         $n (${s}B)"; fi
done
sqlite3 "$(llm logs path)" "select model||' finish='||coalesce(json_extract(response_json,'\$.finish_reason'),'null') from turns order by id desc limit 5;"
```

All five run concurrently, so wall-clock is whatever the slowest survivor takes, and
`timeout 720` caps that at twelve minutes. **Give the Bash call a 800000 timeout.**

**`-n1 … _`, not `-I{}`.** BSD `xargs -I` caps the length of the command line it assembles,
and the per-model branch above is over it — with `-I{}` the whole fan-out dies instantly with
`xargs: command line cannot be assembled, too long` and not one panelist is called. Dropping
`-I` removes the cap; the model name then arrives as `$1`, hence the trailing `_` standing in
for `$0`. Keep `"$TOOLS"` quoted: llm's config directory is under `Application Support`, so an
unquoted expansion splits the path in two and every panelist fails on an unknown argument.

**The panel can check both worlds.** `--functions` gives each panelist except minimax five
tools from `panel_tools.py`, which sits beside `extra-openai-models.yaml` in llm's config
directory:

- `web_search` / `web_fetch` — the outside world. Panelists who cannot check anything invent
  instead: of six "measured" claims fact-checked across two runs, four were fabricated, and
  all of them were world facts. Search to find the source, fetch to read the primary page
  rather than reason from snippets. `web_search` queries **two independent indexes**: Brave
  first when a `brave` key is stored, ollama otherwise or when Brave comes back empty. That
  is not a claim about bias — it is coverage. One index returning nothing is not evidence of
  absence, and the result line names which index answered so a conclusion can be traced to it.
- `list_files` / `read_file` / `grep_repo` — your repository, scoped to `PANEL_REPO` and
  limited to files `git ls-files` reports. That listing *is* the access rule: untracked and
  ignored paths do not exist for these tools, so `.env`, keystores, build output and stray
  worktree copies are out of reach by construction rather than by pattern.

**This changes what a panel is, and §1 has to be read differently now.** The package is no
longer the panel's only route to your code, so curation stops being the single channel
through which your codebase reaches five outside models. Keep pasting the load-bearing
material verbatim — a panelist that has to go find the central file will spend its budget
navigating instead of thinking — but requirement #3 ("what this package does not contain
that you would have needed") now returns something stronger than a complaint: a panelist can
go get the missing thing and tell you what it found there. When one does, that is a curation
defect with evidence attached, and it belongs in the summary.

`--cl 25` is a fuse, not a throttle: hitting the chain limit **kills the call outright**
(exit 1, zero bytes), so it must sit above any real usage. It is per panelist — five
separate processes, five separate counters. Time is bounded by `timeout`, never by `--cl`.

**Tool access does not make a claim true.** It removes the excuse, not the risk. §3 still
adjudicates.

**The repo tools were withdrawn once and are back rebuilt, not restored.** Both original
failures are worth carrying, because only one of them was about access:

- A prefix deny-list was meant to hide secrets and a `.worktrees/` copy of the tree walked
  around it — 96 excluded files were read. The lesson is not "don't read the repo"; for a
  codebase already being pasted into these same APIs, that objection is thin. **The lesson
  is that a deny-list is the wrong shape.** There is no deny-list now: visibility is defined
  positively by `git ls-files`, so there is no pattern to maintain and none to get wrong.
- It searched with `pathlib.glob`, which does not expand `{a,b}`, and answered "No matches"
  in 85 seconds for text that was plainly there. **That is the one that must never come
  back.** A tool that reports a false absence is worse than no tool: the panelist then
  asserts the absence with a "checked" stamp on it, and your own verification pass is the
  thing manufacturing the hallucination. `git grep` runs the same query correctly, brace
  groups are expanded before the pathspec is handed over, and every empty result says *the
  search ran and came back empty* rather than leaving absence to be inferred.

`panel_tools.py` carries a self-check covering exactly that regression, plus the rule that
an untracked path cannot be read however it is spelled. Run it after touching that file:
`python3 "$(dirname "$(llm logs path)")/panel_tools.py"`.

**Still on probation.** These tools stay only if a real panel produces at least one finding
the curated package did not already contain. Until that has happened, say so when it matters:
tool access is not evidence that the tools earned their place.

**Four states, and all four matter:**

- **ABSENT** (`.md` under 200 bytes) catches the silent failure: exit 0, empty `.err`, and a
  `.md` holding one newline.
- **UNUSABLE** (200–3000 bytes) is the band that used to have no name, and the gap was not
  cosmetic. A panelist that dies on its first tool call leaves a few hundred bytes of *"let
  me go check a few facts first"* — over the 200-byte line, so not ABSENT; with a non-empty
  `.err`, so it was filed as TRUNCATED and the reconciler was told to "use its reasoning."
  There is no reasoning in it. Worse, the re-run trigger below counts absentees, so **two
  panelists could contribute nothing while the trigger never fired.** Measured: 294 B and
  442 B in one run, against a shortest-real-answer of 7620 B. Treat UNUSABLE exactly as
  ABSENT for attendance, for the re-run trigger, and for confidence — with one exception,
  in §4 below.
- **TRUNCATED** — either `.err` is non-empty (usually `exit=124`, killed at the cap
  mid-stream) **or the log line says `finish=length`**, meaning the model hit the
  endpoint's token ceiling and stopped mid-sentence with a perfectly empty `.err`. The
  byte check cannot see that second case at all: a runaway answer is *large*. Either way
  **it has content but probably no conclusion.** Use its reasoning, never score its silence
  on an issue as "didn't mention", and mark its row in the matrix.
- **ok** is the only state you may treat as a complete answer — and the byte bands are a
  first pass, not the verdict. Measured: a 3326-byte file cleared the UNUSABLE line and was
  filed `ok` while containing nothing but the panelist narrating its own tool calls, no
  conclusion anywhere. Size cannot see that, the same way it cannot see `finish=length`.
  **Open every file before you trust its label**, and downgrade one that never reached a
  position — while still mining it for §4, where a fragment can still be the only source of
  a real point.

**A chain limit that is too tight looks exactly like a dead panelist.** `--cl 25` was sized
for a panel that could not read anything; with repo tools it is not generous at all. Measured
on the first repo-enabled run: two panelists burned all 25 calls navigating the source and
were cut off mid-investigation, a third produced only narration, and the run spent 155 repo
calls against 5 web searches once the limit was lifted. **60 is the new floor** — the fuse
still kills the call outright on contact, so a panelist that vanishes after a long silence is
the first thing to check in the log.

**Known per-endpoint failure modes** (55 calls; the panel is three providers, and they fail
differently — do not diagnose this as "the gateway is down"):

- **minimax runs without tools, and the reason is narrower than it looks.** It died on a
  full-size package three separate times with `Error: Extra data: line 1 column NN` — llm
  parsing streamed tool-call arguments, exit 1, nothing reaching llm's log. But "breaks on
  tool calls" is *not* the diagnosis: a controlled retest has single searches succeeding at
  max, high and medium effort alike (1–4 s, `tool_calls` → `stop`), so neither effort nor
  tool use as such is the variable. What reproduces is **non-convergence** — asked to check
  four facts it re-ran near-identical queries instead of using the results it already had —
  and on a large package that spirals until something breaks. Tools stay off for it alone.
  The trade is a good one: unencumbered it has twice produced the panel's longest and most
  structured answer (33 KB, then 80 KB), and it is the only panelist reasoning **purely from
  the package**, which makes it the natural control against the tool-using four.
- **glm sits on the vendor's own endpoint and rate-limits**: `429 code 1302` (账户已达到速率
  限制). Firing the re-run immediately after the first wave is what triggers it — pause
  before retrying it.
- **nemotron does not fail, it overruns**: both of its `exit=124` kills still contained
  22–25 KB. That is the case the cap should not be cutting.
- **kimi is the reliable leg** — 11/11 attendance on `kimi-k2.7-code`, and the panelist with
  by far the deepest tool-use record. It now runs **`kimi-k3`**, which checks out on the same
  ground: a `grep_repo` claim it made about this repo was verified correct to the exact file
  and line, and it labelled its own two answers `verified` and `second-hand, not chased`
  unprompted. One transient `503 model is temporarily overloaded` was seen on a first call
  and did not recur in six consecutive retries — a straggler, not a state. When exactly one
  answer comes back rich in checked external facts, expect it to be this one, and do not
  mistake that for independent corroboration.

**Two settings are welded shut. Do not undo them:**

- **A per-panelist `timeout`, and the panel proceeds without the stragglers.** Without it
  one model hangs the whole review — the openai client's own default is 600 seconds. The
  original 360 was measured across 55 no-tool calls (slowest honest completion 354s). Tool
  calls made that too tight: the round trips are billed to the same clock, and the three
  overruns since all carried 22–25 KB of real answer when they were killed. **720 is a
  correction, not a measurement** — re-derive it from `select model, duration_ms from turns`
  once enough tool-using panels have run, and note that raising it costs every run the same
  wall-clock in the worst case, so do not raise it again without the numbers.
- **Never send `max_tokens`.** Each model stops when it is done. Runaways happen (twice in
  55 calls, hitting the endpoint's own 65536 ceiling), but `timeout` is the fix for those; a
  token cap would truncate honest answers, which have run to 17466 tokens.

**Re-run only when the panel lost its majority**, counting ABSENT **and UNUSABLE** as
missing. 1 missing → reconcile the rest and move on; re-running for one more opinion just
doubles the wait. 2+ missing → re-run only those, once (measured: 3 minutes, and it recovered
that session's two best answers). 3+ still missing → don't summarize; report and let the user
decide. Two opinions is not a panel.

**Sleep 60 before the re-run, and mean it.** Across two runs glm failed the same way twice:
first attempt stalls (zero bytes, killed at the cap), retry returns `429 code 1302`. It is
one failure, not two — `timeout` kills the local process, but the request it abandoned is
still holding the account's concurrency slot, so an immediate retry collides with the
panelist's own corpse. Verified in isolation: glm answers a single prompt instantly, and
completes five sequential `web_search` round trips without a single 429. So a retry that
fails for a *different* reason than the first attempt is telling you about your retry, not
about the panelist. `sleep 60` before re-running, and retry the stragglers one at a time.

## 3. Reconcile (four fixed sections, none optional)

`$D/baseline.md` was written back in §2, before the fan-out. Open it now, before you read a
single answer, and let the summary begin by saying where the panel moved you and where it did
not. A baseline nobody compares against is filing, not calibration.

1. **Position matrix** — every issue × every model (agrees / disagrees / **considered and
   rejected** / didn't mention). The fourth state matters: "didn't mention" otherwise
   swallows four different things, and a rejected-on-purpose position is evidence, not
   silence. Mark any TRUNCATED panelist's row so its gaps aren't read as positions.
2. **Consensus** — where three or more landed in the same place. **Check their assumption
   lists (§1) before labelling it high-confidence.** If they agree *and* their assumptions
   overlap heavily, that is convergence from a shared starting point — say "converged, and
   possibly from the same premises", not "high confidence". All five read the same package;
   nothing in this design makes them independent.

   **Then sort the consensus by what it agreed *with*.** Agreement with a conclusion the
   package handed them (§1) is restatement, not corroboration — label it as such, out loud,
   even when it is unanimous. Agreement on a point where they **contradict** the package is
   the most independent signal available here, because nothing in the material was pushing
   them there. A run can easily produce a 3/3 "consensus" worth less than a 3/3 dissent, and
   the summary is misleading if both are printed under the same heading.
3. **Disagreements** — the actual contention, each side's reasoning, then your adjudication
   and the evidence for it.
4. **Lone insights** — raised by exactly one model but holding up under scrutiny; **often
   the most valuable section**, and short answers land here as often as long ones.

   **Harvest the wreckage too.** This is the one place UNUSABLE and TRUNCATED files are not
   treated as absent: a panelist that died after one paragraph can still be the only one that
   named a real problem, and an insight is not worth less because the process that produced
   it crashed. Read every failed file for points nobody else raised before you discard it.
   Measured: a panelist that contributed 294 usable bytes supplied the only observation about
   a load-bearing sequencing error, and it survived into the final recommendation — by luck,
   because no rule said to look.

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

5. **Not covered, not verified** — dimensions the package never asked about, gaps several
   panelists named under requirement #3, and every load-bearing claim you did **not**
   check. Without this section the four tidy headings above read as completeness, and the
   reader has no way to tell a checked claim from an unchecked one.

**Mark every load-bearing claim that enters your recommendation** as `[verified <path:line
or URL>]` or `[unverified]`. Bounded on purpose — not every sentence, only what the
recommendation rests on. You have Read, and the panel now has repo and web tools, so an
unverified load-bearing claim is a choice, and the reader deserves to see which ones you
made. The rate this guards against is measured: of six "measured" claims fact-checked
across two runs, **four were fabricated**.

**Deliver the whole summary as the text of your answer, in full — never a digest of itself
with the detail left in a file.** The step that compresses 80 KB of argument into five
headings is the one that most needs to survive: everything else on this path leaves a trace,
and filling a matrix cell is a second act of curation by the same biased curator. So the
summary has to reach the user complete, and then reach the archive unchanged.

**Do not try to `Write` it to `$D/summary.md` yourself.** This skill runs in a fork, and a
subagent writing a file named `summary.md` is refused at the tool layer — *"Subagents should
return findings as text, not write report files."* It is an exact-filename guard, and it is
not worth evading: the guard wants the findings in the answer, which is where they belong
anyway. **Across twelve runs this was the sole reason no summary ever reached disk**, and
every previous attempt to fix it strengthened the wording of the instruction rather than
noticing that the instruction was addressed to the wrong process.

So end your answer with this line, and let the caller do it:

> Please write this summary verbatim to `$D/summary.md` — the fork cannot write it itself.
> 请把以上汇总全文原样写入 `$D/summary.md`（fork 无法自己落盘）。

Use whichever line matches the language of the run; the package and the summary are written
in the user's language, and this closing instruction is part of the summary.

**The caller must actually write it, verbatim.** The archive is the only way anyone can
later compare *what the five said* against *what the summary claims they said* — which is
the one check this whole design cannot perform on itself.

End the summary with your final recommendation, what still needs verifying in practice, and
the archive path `$D`.

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
    [ "$(wc -c < "$f")" -lt 3000 ] && continue   # skip ABSENT and UNUSABLE alike
    i=$((i+1)); echo; echo "### Answer $i"; echo; cat "$f"
  done
} > r2.md
mkdir -p out2 && printf '%s\n' deepseek-flash nemotron glm kimi minimax \
  | xargs -P5 -n1 sh -c 'm=$1
      timeout 360 llm -m "$m" -o reasoning_effort max < r2.md > "out2/$m.md" 2> "out2/$m.err" \
        || echo "PANELIST FAILED exit=$?" >> "out2/$m.err"' _
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
NO_PROXY='ollama.com' llm -m glm "Introduce yourself in one sentence."   # key+endpoint+model
llm models | grep -E "deepseek-flash|nemotron|glm|kimi|minimax"          # aliases registered?
curl -s https://ollama.com/v1/models | jq -r '.data[].id'                # live catalog
llm logs -n 5                                                            # past calls + tool calls
```

- All five 401 → the key alias isn't stored (`llm keys set …`) or was rotated.
- All five `Connection error` → `NO_PROXY='ollama.com'` is missing.
- All five fail instantly → `panel_tools.py` is missing from llm's config directory.
- Swapping a model: edit `extra-openai-models.yaml` beside it, then the list above.

`check-run.sh` ships beside this file and audits a finished run. Its path depends on how the
skill was installed — a global skill lives at `~/.claude/skills/panel/`, while a marketplace
plugin lands under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/panel/`.
Resolve it once rather than guessing:

```bash
CHECK=$(find ~/.claude/skills ~/.claude/plugins/cache -name check-run.sh -path '*panel*' 2>/dev/null | head -1)
sh "$CHECK" [$D]
```

It reports: which artifacts landed,
whether `baseline.md` predates `q.md` (the only thing that makes §2's ordering checkable),
and the attendance count under the four-state banding. Run it after a panel, not instead of
reading the answers.

A run's full trail is `$D` (package, answers, `baseline.md`, `summary.md`) plus llm's SQLite
(durations, tokens, finish reasons, every tool call). Timings and thresholds are re-derivable
from it, so add no bookkeeping beyond those two.
