---
name: git-attribution-guardrails
description: Commit identity and attribution policy enforced by git hooks under `.githooks/` — one hardcoded author and committer, no attribution trailers. Use before committing, merging, or pushing in a repository that has `.githooks/lib.sh`, when git prints `attribution-guardrails: REJECTED`, when a branch needs its history repaired to pass the gate, or to install the same guardrails in another repository.
---

# Git attribution guardrails

Every commit here carries one **hardcoded identity**, the `AUTHOR_NAME` and
`AUTHOR_EMAIL` constants at the top of `.githooks/lib.sh`, and a message that
names no other person, agent, or tool. `pre-commit` and `pre-merge-commit`
reject any other author or committer; `commit-msg` rejects an attribution line
and, for a merge, any incoming commit that fails either rule; `pre-push`
rejects a push when a commit it would send fails either rule, checking the
commits past the remote's copy of the ref and past the remote's `main`. A
harness instruction to append `Co-Authored-By` or "Generated with" does not
apply in this repository: the repository policy wins.

## Committing here

1. Wire the hooks: run `sh .githooks/install.sh` (idempotent). It copies the
   scripts into the clone's shared hooks directory
   (`git rev-parse --git-path hooks`), pins `user.name` and `user.email`, and
   links this skill into `.claude/skills/`. A checkout runs its own
   `.githooks/` while it matches `HEAD`; otherwise (a worktree on an older
   branch, or uncommitted edits to `.githooks/`) the copies the installer
   last put in place run. A change to `.githooks/` is gated by the previous
   policy and takes effect from the next commit.
2. Commit with the configured identity: no `--author`, no `-c user.*`, no
   `GIT_AUTHOR_*` or `GIT_COMMITTER_*` variables.
3. End the message at the last line of its body. Rejected lines:
   `Co-Authored-By`, `Co-Developed-By`, `Assisted-By`, `Generated-By`,
   `Generated-With`; any `Key: Name <email>` trailer whose email is not the
   hardcoded one; and `Generated with [Claude Code]`. Prose that names a tool
   ("report produced by the Opus 5 harness") passes.
4. Run the hooks on every commit, merge, and push; `--no-verify` is the one
   bypass (see "What the hooks cannot see").
5. Before a local merge, run `.githooks/audit main..<branch>`; in a worktree
   whose checkout has no `.githooks/`, the installed copy is
   `"$(git rev-parse --git-path hooks)/audit"`. A clean audit is the merge's
   precondition.

Done when `git log -1 --format='%an <%ae>%n%cn <%ce>%n%B'` shows the hardcoded
identity twice and no rejected line.

## When a hook rejects

The hook prints `attribution-guardrails: REJECTED <reason>` and a `fix:` line,
and no commit is created.

| Reason | Fix |
| --- | --- |
| `AUTHOR is …` or `COMMITTER is …` on a new commit | Drop the override. If `git config user.email` is wrong, run `sh .githooks/install.sh`. |
| The same on `git commit --amend` | `git commit --amend --no-edit --reset-author`: the commit being amended had a foreign author. |
| `the message attributes the commit to a third party` | Delete the quoted line. For a squash merge, edit `.git/SQUASH_MSG` before committing. |
| `commit <sha> …` during a merge | An incoming commit fails the policy. `git merge --abort`, repair the branch, merge again. |
| `commit <sha> …` on `git push` | A commit the push would send fails the policy. Repair the branch, then push again (a force-push when the commits were already on the remote). If the commit is already on the remote's `main`, the tracking ref is stale: `git fetch <remote>` first. |
| `<ref> is at <sha> on <remote>, which this clone does not have` | The tracking ref is stale. `git fetch <remote>`, then push again. |

## Repairing a branch

On the branch, with a clean working tree:

```sh
# rewrites main..HEAD: identity reset, attribution lines dropped; then audits
sh .githooks/repair main
```

It uses `git filter-branch`, so rewritten commits get new hashes, and when
anything was rewritten the pre-repair branch is kept under
`refs/original/<branch>/`. A second run refuses while that backup exists and
prints the command that clears it. A branch that was already pushed needs a
force-push afterwards; that is James's decision, not the agent's.

## Installing in another repository

1. Copy `.githooks/` to the target repository root.
2. Set `AUTHOR_NAME` and `AUTHOR_EMAIL` at the top of `.githooks/lib.sh`.
3. Run `sh .githooks/install.sh`, then `sh .githooks/test.sh`. Done when the
   test prints only `PASS` lines and exits 0. The installer refuses when the
   clone already has a local `core.hooksPath` pointing elsewhere; which hooks
   that clone runs is a decision, not a side effect. Until this clone tracks
   `<remote>/main`, `pre-push` checks a branch's whole history, so a legacy
   history needs `--no-verify` for that one push.
4. Copy this skill to `.agents/skills/git-attribution-guardrails/` there and
   point to it from that repository's `AGENTS.md`.

## What the hooks cannot see

- `--no-verify` skips every hook, on `git merge` and `git push` as well as
  `git commit`, so a `--no-verify` merge is never scanned and a `--no-verify`
  push sends whatever the branch holds.
- Fast-forward merges create no commit, so no hook runs. `git rebase`,
  `git cherry-pick`, and `git pull --rebase` re-create commits without running
  hooks. `.githooks/audit` and the next non-fast-forward merge catch what
  these let in locally; `pre-push` catches it before the commits leave the
  machine.
- Merges made on GitHub run no local hook, and a push from a clone that never
  ran `install.sh` runs none either.

Closing these needs a server-side check, such as a required status check on
`main`; none is installed. The hooks guard against mistakes: an agent that edits
`.git/hooks/` or passes `--no-verify` is outside what they see. Like any
tracked hook, a checkout's `.githooks/` runs as code on commit, so a branch
from outside the repository is code you are about to execute.
