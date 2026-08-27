# panel — why the rules are what they are

Case notes for `SKILL.md`. **Nothing here is needed to run a panel.** Read a section when
you are about to change the thing it describes, or when its symptom shows up — the skill
points here at both moments.

Every entry is a measurement from a real run, not a rationale invented afterwards. That is
also the standard for adding to this file: if a rule cannot point at a run that went wrong,
it should not be a rule.

## fan-out

**Change nothing in that command block without reading this.** Every flag in it was set by
a failure, and each one fails in a way that does not look like the flag.

- **`-n1 … _`, never `-I{}`.** BSD `xargs -I` caps the length of the command line it
  assembles, and the per-model branch is over the cap. With `-I{}` the whole fan-out dies
  instantly — `xargs: command line cannot be assembled, too long` — and **not one panelist
  is called**. Dropping `-I` removes the cap; the model name then arrives as `$1`, which is
  what the trailing `_` is for.
- **`"$TOOLS"` stays quoted.** llm's config directory is under `Application Support`. An
  unquoted expansion splits the path in two and every panelist dies on an unknown argument.
- **`timeout 720`, per panelist, and the panel proceeds without stragglers.** Without a
  timeout one model hangs the whole review. The original 360 was measured across 55 no-tool
  calls, slowest honest completion 354 s. Tool calls made that too tight — round trips are
  billed to the same clock — and the three overruns since each still held 22–25 KB of real
  answer when they were killed. **720 is a correction, not a measurement**: re-derive it
  from `select model, duration_ms from turns` once enough tool-using panels have run, and
  remember raising it costs every run the same wall-clock in the worst case.
- **`--cl 60` is a fuse, not a throttle.** Hitting the chain limit kills the call outright —
  exit 1, zero bytes — so it must sit above real usage, never at it. At the old `--cl 25`
  two panelists burned every call navigating the source and were cut off mid-investigation,
  and a third produced only narration. A repo-heavy question spends repo calls at roughly
  thirty times the rate of web searches (155 vs 5 in one run).
- **No `max_tokens`, ever.** Each model stops when it is done. Runaways happen — twice in 55
  calls, hitting the endpoint's own 65536 ceiling — but `timeout` is the fix for those. A
  token cap truncates honest answers, which have run to 17466 tokens.
- **No `-o reasoning_effort` in the fan-out.** An explicit `-o` outranks every stored
  default, which would make per-model effort configuration unusable. Effort lives in
  `llm models options set <alias> reasoning_effort <tier>`, beside the endpoint and key.
  An unset default does not error — it runs at whatever the server picks and the answer
  looks completely normal — which is why the preflight is a hard gate rather than a warning.
- **No `--key` on the command line.** It overrides every `api_key_name` at once while
  leaving each `api_base` alone, so one key is presented to three providers and the two that
  did not issue it answer `401`. Symptom: *some* panelists 401 while others work.

## thresholds

**200 / 3000 bytes.** Mirrored in the fan-out block and in `check-run.sh` — change both.

- Under 200 B is the silent failure: exit 0, empty `.err`, a file holding one newline.
- 200–3000 B is a panelist that died on its first tool call, leaving *"let me go check a few
  facts first"* and nothing else. Measured at 294 B and 442 B in one run, against a
  shortest-real-answer of 7620 B. Before this band existed those two were filed as
  TRUNCATED, the reconciler was told to "use its reasoning" — there was none — and the
  re-run trigger counted only absentees, so **two panelists contributed nothing while the
  trigger never fired.**
- Bands are a first pass, not a verdict. A 3326 B file once passed as `ok` containing
  nothing but a panelist narrating its own tool calls. Size cannot see that, the same way it
  cannot see `finish=length` — a runaway answer is *large*.

## per-panelist

- **minimax runs without tools.** Not because tool calls break it — single searches succeed
  at every effort tier in seconds — but because it **fails to converge**: asked to check
  four facts it re-ran near-identical queries instead of using results it already had, and
  on a full-size package that spirals until something breaks (three times, each with
  `Error: Extra data: line 1 column NN` as llm parsed streamed tool-call arguments).
  Unencumbered it has twice produced the panel's longest answer.
- **glm stalls, then 429s on the retry.** Twice: the first attempt returns zero bytes and is
  killed locally, but the abandoned request still holds the account's concurrency slot, so
  an immediate retry collides with the panelist's own corpse and returns `429 code 1302`.
  One failure, read as two. Verified in isolation: glm answers a single prompt instantly and
  completes five sequential `web_search` round trips without a single 429.
- **nemotron overruns rather than fails** — both `exit=124` kills still held 22–25 KB.
- **kimi is the reliable leg** and by far the deepest tool user — 11/11 attendance across the
  measured runs. A `grep_repo` claim it made about this repo checked out to the exact file
  and line, and it labelled its own answers `checked` and `second-hand, not chased` without
  being asked.

## the summary that never reached disk

Twelve consecutive runs produced no `summary.md`. The cause was not the model: this skill
runs in a fork, and a subagent writing a file named `summary.md` is refused at the tool
layer — *"Subagents should return findings as text, not write report files."* `q.md` and
`baseline.md` written from the same fork went through fine; it is an exact-filename guard.

Every earlier attempt to fix it strengthened the wording of the instruction, which is the
diagnostic lesson worth keeping: **the instruction was addressed to the wrong process.** The
fix is a handoff line to the caller, not a firmer imperative.

## the repo tools, withdrawn and rebuilt

Full history lives in `panel_tools.py`'s module docstring, at the site. In brief: a prefix
deny-list was walked around by a `.worktrees/` copy of the tree, and a `pathlib.glob` search
spent 85 seconds answering "No matches" for text that was plainly present. The first is why
visibility is now defined positively by `git ls-files`; the second is why the base is
`git grep` and why every empty result must say the search *ran*.

## what the guards are worth

- **Fabrication, measured**: of six "measured" claims fact-checked across two tool-less runs,
  **four were fabricated** — all world facts, in the same confident register as the true
  ones. This is what the stamps and the panel's web tools are for.
- **Overstatement, measured**: two panelists reported a database "had been seeded" when the
  repository proved only that a seed script and a deploy recipe existed. **Every path and
  line number they cited was real** — a two-valued stamp had nothing to object to. Hence
  three stamps, and the rule that a static artifact cannot verify a claim about execution.
- **Correlated blind spot, measured**: five panelists, three with repo tools, 155 repo calls
  between them, and **0/5** noticed that one system verified signatures on the server and
  never on the client. It reached the summary only because the reconciler compared against
  the baseline by hand — which is why baseline entries are now matrix rows by rule.
- **Wreckage is worth mining**: a panelist that contributed 294 usable bytes supplied the
  only observation about a load-bearing sequencing error, and it survived into the final
  recommendation by luck, because no rule said to look.
