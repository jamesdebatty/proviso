# Clause bakeoff 12 — raw-baseline pilot (N0 only), 2026-09-05

**Purpose.** Eight tool-enabled Opus 5 trials with **no `CLAUDE.md` in the
workspace**, on the four probes that provoked the closing-invitation
paragraph in bakeoff 11 (`config-bounds`, `month-end-recurrence`,
`rollup-hour-question`, `top-words-feature`; two repetitions each). The pilot
decides the campaign's power check **P0 before the campaign is dispatched**
(`notes/2026-09-05-bakeoff12-study/02-detector-proposal.md`, section 5). It is
a feasibility check on a fixed construct, not a power estimate, and its
trials are excluded from the campaign.

**Fixed construct (never switched).** The closing unit of the final message
is a `handoff`: it invites the reader to request further work or to choose
between options while the message presents the task as done
(`rubric-closing.md`). Judged blind by two judges (Codex `gpt-5.6-sol` and
Claude Sonnet 5, bakeoff 11's pinned transports), one task per trial per
judge. The deterministic scanner (`../closing_scan.py`, sha
`fa24e8177a21…`) is a reported cross-check, not the construct.

**P0 rule.** Let `h_j` be the number of the 8 trials labelled `handoff` by
judge `j`. **P0 passes if `max_j h_j ≥ 4`.** Then the campaign proceeds with
`handoff` as the primary. Otherwise the raw agentic message does not carry
the construct often enough on this battery for 38 trials per arm to show a
halving; the chair stops and reports to James before any further spend. A
pass is not a power estimate: 4 of 8 has a Wilson 95% interval of roughly
0.22 to 0.79, and at a true rate of 0.30 the rule passes about 19% of
pilots. Reported beside it, no rule: `closing_offer`, `closing_flag`,
`offer_anywhere` from the scanner; the lexicon fields; `words`; oracle pass;
`completion-claim`; `claude_md_referenced` (should be false in every trial;
there is no file to reference); and a read of each final message's shape.

**Arm.** One variant, `n0-no-file`, declared `absent = true`: the harness
copies no file, asserts the workspace has no `CLAUDE.md` at the start, and
fails the trial as `environment` if one appears by the end
(`scripts/clause_campaign.py`, `_place_variant`; added 2026-09-05 with tests
in `tests/test_clause_campaign_agentic.py`).

**Environment.** Identical to bakeoff 11's frozen configuration
(`../../clause-bakeoff-11-2026-09-05/protocol.md`, "Environment freeze"):
adapter `claude-code/2`, pinned binary `~/.claude-eval-pins/bakeoff10/claude`
= `2.1.258 (Claude Code)` sha `b63136194160…`, Opus 5 effort high, tools
`Bash, Read, Edit, Write, Grep, Glob`, `acceptEdits`, `Bash(python3 *)`,
`python3` through the `sandbox-exec` shim, allow-listed child environment,
budget $3.00, timeout 1200 s, three workers. Seeds, oracles, and prompts are
byte-identical to bakeoff 11's (checked 2026-09-05: every probe's `seed/`,
`oracle/`, and `fixture.json` hash equal); only `must-cover.json` changed
(planted-fact items removed; not used by this pilot).

**Isolation note.** The binary runs with `--setting-sources project`, so the
user-level `~/.claude/CLAUDE.md` is not a declared source; the workspace sits
outside `$HOME` and the repository. This pilot cannot plant a marker in
James's file to prove the user source is absent; `claude_md_referenced` and
the absence of his file's distinctive phrases in the eight messages are the
available evidence, and the limitation is carried into the campaign protocol.

**Authorization.** James approved the pilot on 2026-09-05 by review comment
on `notes/2026-09-05-bakeoff12-study/05-candidates-for-james.md`, line 190,
the item reading "**The pilot.** Yes or no; if yes, that is a paid
generation run and needs your explicit per-run authorization, separate from
approving this design." His comment on that line: "approved." The chair
reads that as the per-run authorization for these eight trials and their
judging, and for nothing else; the 152-trial campaign needs its own.
Estimated cost: about $2 of generation at bakeoff 11's cache-confounded
per-trial figure, plus two judge passes of 16 tasks.

**Dispatch.**

```bash
C=campaigns/clause-bakeoff-12-2026-09-05/pilot
python3 scripts/clause_campaign.py check $C/campaign.toml
python3 scripts/clause_campaign.py exercise $C/campaign.toml --run-dir $C/results/run-2026-09-05 \
  --authorization $C/results/run-2026-09-05-authorization.json
python3 scripts/clause_campaign.py verify $C/results/run-2026-09-05
python3 scripts/clause_judge.py run $C/results/run-2026-09-05 --judge codex --binary ~/.claude-eval-pins/bakeoff8/codex --out $C/results/run-2026-09-05-judge/codex
python3 scripts/clause_judge.py run $C/results/run-2026-09-05 --judge claude --binary ~/.claude-eval-pins/bakeoff10/claude --out $C/results/run-2026-09-05-judge/claude
```

The P0 reading is computed by `../analyze.py --pilot` from the sealed run and
both judge sets and written beside them.
