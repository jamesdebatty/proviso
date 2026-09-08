# Clause bakeoff 11 — canary C (dontAsk permission mode)

Date: 2026-09-05. Status: throwaway harness check, **not campaign evidence**.
Three trials on one probe (`top-words-feature`), variants A1, DEP, and M1
(A1 plus one sentence demanding the literal token `ZQX-MARKER` at the end of
the final message). Purpose, fixed before dispatch (see
`../protocol.md`, "Canary"): confirm on the pinned 2.1.258 binary that under
`claude-code/2` (a) `Bash(python3 *)` allows `python3 -m unittest` and other
commands are denied with the session continuing to a `success` result;
(b) `_answer_models` stays `["claude-opus-5"]` in a tool-enabled session;
(c) project `CLAUDE.md` is applied under `--restricted` (M1's token appears);
(d) the sandboxed python3 shim runs the seed's tests and the oracle;
(e) per-trial cost and duration, to size the budget cap and the schedule.
Canary trials are excluded from the campaign analysis; their cost is reported.
Authorized by James's instruction quoted in
`../../../notes/2026-09-05-bakeoff11-council/00-brief.md` and reaffirmed at
02:48 (`07-chair-log.md`).


## Canary C

Run after canary A showed that under `acceptEdits` Claude Code auto-approved a
read-only `find` command that is not `python3`, so it ran outside the sandbox
shim. Canary C repeats A1 and M1 on `top-words-feature` with
`permission_mode = "dontAsk"` and `allowed_tools = ["Edit", "Write", "Bash(python3 *)"]`
(file tools stay confined to the workspace by `--restricted`) to see whether
non-python3 commands are then denied while edits and the tests still run.
