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

- **`\$1`, escaped, and it is not optional.** Claude Code substitutes `$ARGUMENTS`, `$0`,
  `$1`, `$2` … when it renders a skill into the model's context, **and code fences are not
  excluded** — only `` ```! `` injection blocks get special treatment. A bare `$1` therefore
  reaches the executing model already replaced by the caller's first argument, and copying
  the block runs `llm -m <whatever that was>` for all five. The escape is a single backslash
  directly before the token; `\\$1` does not work. Discovered the hard way: the block had
  been unescaped since it was written, and every run that "worked" worked because the fork
  noticed the breakage and improvised around it — in one case by writing its own `rerun.sh`.
  **This is also the one failure mode that no panelist can find for you**: they read the file
  from disk, where the text is intact; only the model being driven by the rendered prompt
  ever sees the damage. `[verified-live` a throwaway skill containing both forms, invoked
  with known arguments: the bare `$1` came back as the caller's second whitespace token, the
  escaped one came back as a literal `$1`, and a ```bash fence changed neither `]`.
  Note the indexing while you are here: `$1` is `$ARGUMENTS[1]`, i.e. the **second** token.
- **Background, *and then wait*.** The first run under the "put it in the background"
  instruction abandoned itself: the fork launched the fan-out, had nothing left to do in that
  turn, and ended — five panelists answered into an archive nobody was reading. Fixing the
  600 s ceiling introduced a worse failure than the ceiling. Launch and block; the triage
  loop rides in the same background call so its completion is the signal.
- **The 600 s ceiling itself.** A foreground Bash call is capped at 600 s and
  `timeout 720` is longer than that, so a foreground run is killed mid-block: the answers are
  already on disk but the triage loop and the log probe never execute. The old instruction
  ("give the Bash call a 800000 timeout") asked for a value above the tool's own maximum and
  was silently clamped.

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
- **One retry, and only for a failure that came back fast** (under 120 s). Two failure modes
  are cheap to re-draw and cost a whole seat when they aren't: a rate-limit rejection that
  never reached the model, and **exit 0 with too little text** — the gateway returned 1 byte
  and a clean exit twice in 14 calls, which the old `||` could not see at all, so the seat was
  scored as present-but-empty. **The bar is the UNUSABLE threshold (3000), not ABSENT (200)**:
  attendance already scores anything under 3000 as absent, so a floor of 200 forfeits a seat
  it could have re-drawn — measured, a panelist returned 788 B and exit 0 in 36 s and the
  first version of this retry let it through. A `timeout` kill is the opposite case: it means the panelist
  tool-looped past its budget and will do it again, so re-running burns another 720 s to fail
  identically. The first attempt's stderr is kept as `out/<m>.try1.err`; the second attempt
  overwrites `out/<m>.err`, so without that copy a retried seat is indistinguishable from a
  clean one, and "this one always needs a retry" is exactly the signal that its route should
  change. **The retry is not the fix for glm** — see per-panelist; a stronger version of it
  (`sleep 60`) has already been measured failing there.

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
  **The `sleep 60` remedy failed once** — a retry run alone, after the pause, still returned
  `429`. One observation, not enough to rewrite the rule, but enough that a second glm
  absence should not be read as "the retry was done wrong".
  **So the entry point is the stall, not the 429** — the three `429`s in runs `20260826-121859`
  / `161300` / `20260827-103114` (`exit=1`, zero bytes, no `turns` row in llm's SQLite: the
  request never reached the model) are the wake of an earlier timeout, not independent
  faults. Retrying attacks the wake; only finishing inside the budget attacks the cause.
  **glm therefore runs at `reasoning_effort high`, alone among the five** — set
  2026-08-27, `llm models options set glm reasoning_effort high`. This is a real exception to
  "always max", taken on the ground that **an absent panelist contributes zero argument**:
  the rule buys reasoning depth, and glm at max was buying none. Revisit if a run at `high`
  still stalls — the next lever is dropping its tools (as minimax already runs), because both
  glm timeouts spent the whole 720 s on tool-call narration and never reached a conclusion.
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
