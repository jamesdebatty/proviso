#!/bin/sh
# Self-test: installs these hooks into a throwaway repo and exercises every gate.
# Exit 0 = every case passed. Usage: sh .githooks/test.sh
set -u
unset CDPATH
HOOKS_SRC=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
git init -q -b main "$T/repo"
cd "$T/repo" || exit 2
cp -R "$HOOKS_SRC" .githooks
# Enforcement is exercised against an identity this throwaway repo configures for
# itself, never the maintainer's; the tracked lib.sh ships blank. Drop whatever
# override the source checkout carries before writing the fixture's own.
rm -f .githooks/identity.local.sh
cat > .githooks/identity.local.sh <<'FIXTURE_IDENTITY'
AUTHOR_NAME='Fixture Maintainer'
AUTHOR_EMAIL='fixture-maintainer@example.invalid'
FIXTURE_IDENTITY
# Gitignored here as it is in the real repositories, so `git add .githooks` never
# tracks it and setting it aside later does not count as a change to the policy.
printf '.githooks/identity.local.sh\n' > .gitignore
sh .githooks/install.sh >/dev/null
# shellcheck source=lib.sh
. ./.githooks/lib.sh
failed=0
n=0

# The tracked policy ships with no identity. Checked as "exactly one assignment
# of each, and both empty", so a re-assignment further down the file cannot pass.
blank_template() {
  for var in AUTHOR_NAME AUTHOR_EMAIL; do
    count=$(grep -c "^$var=" "$HOOKS_SRC/lib.sh")
    value=$(grep "^$var=" "$HOOKS_SRC/lib.sh" | sed "s/^$var=//")
    if [ "$count" != 1 ] || [ "$value" != "''" ]; then
      failed=1; echo "FAIL  tracked lib.sh ships a blank $var (found $count assignment(s): $value)"
      return
    fi
  done
  echo "PASS  tracked lib.sh ships a blank identity"
}
blank_template

# changef FILE COMMAND...: stage a fresh change to FILE, then run the command. change: same, on file f.
changef() { file=$1; shift; n=$((n + 1)); echo "$n" >> "$file"; git add "$file"; "$@"; }
change() { changef f "$@"; }

# expect pass|reject DESCRIPTION COMMAND...: a reject must come from the hook and leave HEAD untouched.
expect() {
  want=$1; desc=$2; shift 2
  before=$(git rev-parse -q --verify HEAD 2>/dev/null || echo none)
  if out=$("$@" 2>&1); then got=pass; else got=reject; fi
  after=$(git rev-parse -q --verify HEAD 2>/dev/null || echo none)
  case "$want:$got" in
    pass:pass) echo "PASS  $desc" ;;
    reject:reject)
      if printf '%s' "$out" | grep -q 'attribution-guardrails: REJECTED' && [ "$before" = "$after" ]; then
        echo "PASS  $desc"
      else
        failed=1; echo "FAIL  $desc (rejected, but not by the hook or HEAD moved)"; printf '%s\n' "$out" | sed 's/^/      /'
      fi ;;
    *) failed=1; echo "FAIL  $desc (expected $want, got $got)"; printf '%s\n' "$out" | sed 's/^/      /' ;;
  esac
}

expect pass   "clean commit"                              change git commit -q -m "one"
expect reject "--author third party"                      change git commit -q -m "x" --author="Claude <noreply@anthropic.com>"
expect reject "GIT_COMMITTER_* override"                  change env GIT_COMMITTER_NAME=Bot GIT_COMMITTER_EMAIL=bot@example.com git commit -q -m "x"
expect reject "-c user.email override"                    change git -c user.email=noreply@anthropic.com commit -q -m "x"
expect reject "Co-Authored-By trailer"                    change git commit -q -m "x" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
expect reject "lower-case co-authored-by"                 change git commit -q -m "x" -m "co-authored-by: Codex <codex@openai.com>"
expect reject "Claude Code promo line"                    change git commit -q -m "x" -m "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
expect reject "Signed-off-by third party"                 change git commit -q -m "x" -m "Signed-off-by: Cursor Agent <cursoragent@cursor.com>"
expect pass   "Signed-off-by hardcoded identity"          change git commit -q -m "x" -m "Signed-off-by: $AUTHOR_NAME <$AUTHOR_EMAIL>"
expect pass   "prose naming a tool"                       change git commit -q -m "notes: eval report produced by the Claude Opus 5 harness"
expect pass   "URL in angle brackets"                     change git commit -q -m "x" -m "Link: <https://example.com/a>"

printf 'Co-Authored-By: Claude <noreply@anthropic.com>\n' > fixture.md; git add fixture.md
expect pass   "trailer text only inside the -v diff"      env GIT_EDITOR="sed -i.bak '1s/^/add fixture/'" git commit -q -v

# A branch with a foreign author and a trailer, committed past the hooks with --no-verify.
git checkout -q -b dirty
changef d git commit -q --no-verify -m "dirty" -m "Co-Authored-By: Claude <noreply@anthropic.com>" --author="Claude <noreply@anthropic.com>"
git checkout -q main
git merge -q --squash dirty >/dev/null
expect reject "squash-merge message carrying a trailer"   git commit -q -F .git/SQUASH_MSG
git reset -q --hard
expect reject "audit flags the dirty branch"              .githooks/audit main..dirty
expect reject "merge: incoming commit fails the policy"   git merge -q --no-ff -m "merge dirty" dirty
expect reject "git commit cannot complete that merge"     git commit -q -m "merge dirty"
git merge --abort

git checkout -q -b clean main
changef g git commit -q -m "clean branch"
git checkout -q main
change git commit -q -m "main moves on"
expect reject "merge: GIT_COMMITTER_* override"           env GIT_COMMITTER_NAME=Bot GIT_COMMITTER_EMAIL=bot@example.com git merge -q --no-ff -m "merge clean" clean
git merge --abort 2>/dev/null
expect pass   "merge: clean branch"                       git merge -q --no-ff -m "merge clean" clean

git checkout -q dirty
expect reject "amend keeps the foreign author"            git commit -q --amend --no-edit
expect pass   "repair rewrites the branch"                sh .githooks/repair main
expect pass   "audit after repair"                        .githooks/audit main..dirty
git checkout -q main
expect pass   "merge: repaired branch"                    git merge -q --no-ff -m "merge dirty" dirty
change git commit -q --no-verify -m "foreign" --author="Claude <noreply@anthropic.com>"
expect reject "amend of a foreign-author commit"          git commit -q --amend --no-edit
expect pass   "amend --reset-author"                      git commit -q --amend --no-edit --reset-author

# Known gaps: rebase and cherry-pick re-create commits without running hooks; audit is the backstop.
git checkout -q -b gap main
changef k git commit -q --no-verify -m "gap" -m "Co-Authored-By: Claude <noreply@anthropic.com>" --author="Claude <noreply@anthropic.com>"
git checkout -q main
expect pass   "cherry-pick runs no hook (known gap)"      git cherry-pick gap
expect reject "audit catches the cherry-picked commit"    .githooks/audit HEAD~1..HEAD
git reset -q --hard HEAD~1
changef m git commit -q -m "main moves again"
git checkout -q gap
expect pass   "rebase runs no hook (known gap)"           git rebase -q main
expect reject "audit catches the rebased commit"          .githooks/audit main..gap
pre=$(git rev-parse gap)
expect pass   "repair the rebased branch"                 sh .githooks/repair main
expect reject "second repair refuses to clobber backup"   sh .githooks/repair main
if [ "$(git rev-parse refs/original/gap/refs/heads/gap)" = "$pre" ]; then
  echo "PASS  backup still holds the pre-repair commit"
else
  failed=1; echo "FAIL  backup still holds the pre-repair commit"
fi
git checkout -q main

# Hooks must fire in a linked worktree whose checkout has no .githooks/ on disk.
git worktree add -q --detach "$T/wt" main
expect reject "linked worktree without .githooks rejects" git -C "$T/wt" -c user.email=noreply@anthropic.com commit -q --allow-empty -m "x"
git worktree remove --force "$T/wt"

# install.sh must be rerunnable, refuse someone else's hook without copying anything, and replace an
# older copy of its own.
expect pass   "install.sh reruns cleanly"                 sh .githooks/install.sh
printf '#!/bin/sh\n# husky\nexit 0\n' > .git/hooks/commit-msg
printf '#!/bin/sh\ncheck_ident AUTHOR\n' > .git/hooks/lib.sh
expect reject "install.sh refuses a foreign hook"         sh .githooks/install.sh
if cmp -s "$HOOKS_SRC/lib.sh" .git/hooks/lib.sh; then failed=1; echo "FAIL  refusal copied nothing"; else echo "PASS  refusal copied nothing"; fi
rm .git/hooks/commit-msg
expect pass   "install.sh replaces an older copy of its own" sh .githooks/install.sh
if cmp -s "$HOOKS_SRC/lib.sh" .git/hooks/lib.sh; then echo "PASS  replaced copy matches"; else failed=1; echo "FAIL  replaced copy matches"; fi
expect pass   "commit after rerun"                        change git commit -q -m "x"
expect pass   "commit with CDPATH exported"               change env CDPATH=. git commit -q -m "x"

# A checkout runs its own .githooks/ only while it matches HEAD; an uncommitted edit to it falls back to
# the installed copies, so editing lib.sh locally changes nothing.
git add .githooks && git commit -q -m "track hooks"
sed -i.bak "s/^AUTHOR_EMAIL=.*/AUTHOR_EMAIL='attacker@example.com'/" .githooks/lib.sh
expect reject "uncommitted lib.sh edit changes nothing"   change git -c user.email=attacker@example.com commit -q -m "x"
cp "$HOOKS_SRC/lib.sh" .githooks/lib.sh

# Once committed, the checkout's hooks are the policy, not the installed copies: each hook, exec bit or not.
tracked_hook_runs() {  # HOOK DESCRIPTION COMMAND...
  hook=$1; desc=$2; shift 2
  printf 'reject "tracked %s ran" "restore .githooks/%s"\n' "$hook" "$hook" >> ".githooks/$hook"
  git add ".githooks/$hook" && git commit -q -m "edit $hook"
  out=$("$@" 2>&1)
  case "$out" in
    *"tracked $hook ran"*) echo "PASS  $desc" ;;
    *) failed=1; echo "FAIL  $desc"; printf '%s\n' "$out" | sed 's/^/      /' ;;
  esac
  git merge --abort 2>/dev/null || true
  cp "$HOOKS_SRC/$hook" ".githooks/$hook"
  git add ".githooks/$hook" && git commit -q -m "restore $hook"
}
tracked_hook_runs pre-commit "tracked pre-commit runs over the installed copy"   change git commit -q -m "x"
tracked_hook_runs commit-msg "tracked commit-msg runs over the installed copy"   change git commit -q -m "x"
git config core.fileMode false
chmod -x .githooks/pre-commit
tracked_hook_runs pre-commit "tracked pre-commit runs without its exec bit"      change git commit -q -m "x"
chmod +x .githooks/pre-commit
git config core.fileMode true
git checkout -q -b side2 main; changef s2 git commit -q -m "side2"; git checkout -q main; changef s3 git commit -q -m "main again"
tracked_hook_runs pre-merge-commit "tracked pre-merge-commit runs over the installed copy" git merge -q --no-ff -m "merge side2" side2
# pre-push checks the commits past the remote's copy of each ref and past the remote's main.
git init -q -b main --bare "$T/remote.git"
git remote add origin "$T/remote.git"
expect pass   "push: main"                                git push -q origin main
git checkout -q -b bad main
changef p git commit -q --no-verify -m "bad" -m "Co-Authored-By: Claude <noreply@anthropic.com>" --author="Claude <noreply@anthropic.com>"
expect reject "push: new branch with a --no-verify commit" git push -q origin bad
expect pass   "push --no-verify skips pre-push (known gap)" git push -q --no-verify origin bad
changef q git commit -q -m "clean on top"
expect pass   "push: only commits past the remote's copy"  git push -q origin bad
git checkout -q main && git merge -q --ff-only bad
expect reject "push: main fast-forwarded onto the bypass"  git push -q origin main
git reset -q --hard origin/main && git checkout -q bad
git clone -q "$T/remote.git" "$T/other" && git -C "$T/other" -c user.name=Other -c user.email=other@example.com commit -q --allow-empty -m "elsewhere" && git -C "$T/other" push -q --force origin HEAD:bad
expect reject "push: remote moved to a commit not here"    git push -q --force origin bad
git fetch -q origin
expect pass   "repair before force-push"                  sh .githooks/repair main
expect pass   "push: force-push of the repaired branch"   git push -q --force origin bad
expect pass   "push: delete a remote branch"              git push -q origin :bad
git checkout -q main
tracked_hook_runs pre-push "tracked pre-push runs over the installed copy" git push -q origin main
# A committed policy that differs from the installed one is the one in force. The
# local override outranks either, so it stands aside for this case.
mv .githooks/identity.local.sh "$T/identity.local.sh.off"
sed -i.bak "s/^AUTHOR_NAME=.*/AUTHOR_NAME='Other'/;s/^AUTHOR_EMAIL=.*/AUTHOR_EMAIL='other@example.com'/" .githooks/lib.sh
git add .githooks/lib.sh && git commit -q -m "policy change"
expect pass   "committed policy that differs is in force"  change git -c user.name=Other -c user.email=other@example.com commit -q -m "x"
cp "$HOOKS_SRC/lib.sh" .githooks/lib.sh
mv "$T/identity.local.sh.off" .githooks/identity.local.sh
git add .githooks/lib.sh && git commit -q -m "restore policy"

# A moved clone keeps its installed hooks: git's default hooks directory, no absolute path in config.
cd "$T" && mv repo repo2 && cd repo2 || exit 2
mv .githooks .githooks.off
expect reject "moved clone still rejects"                 git -c user.email=noreply@anthropic.com commit -q --allow-empty -m "x"

# With no identity pinned — the state this repository ships in — install.sh leaves a
# contributor's own git config alone and the identity checks stand down, but the
# attribution rules still hold.
git init -q -b main "$T/unpinned"
cd "$T/unpinned" || exit 2
cp -R "$HOOKS_SRC" .githooks
rm -f .githooks/identity.local.sh
git config user.name 'Contributor'
git config user.email 'contributor@example.invalid'
sh .githooks/install.sh >/dev/null
if [ "$(git config user.name)" = Contributor ] && [ "$(git config user.email)" = contributor@example.invalid ]; then
  echo "PASS  unpinned: install.sh left the contributor's git config alone"
else
  failed=1; echo "FAIL  unpinned: install.sh rewrote the contributor's git config"
fi
expect pass   "unpinned: the contributor's own identity commits"  change git commit -q -m "one"
expect pass   "unpinned: contributor signs off their own work"    change git commit -q -s -m "x"
expect reject "unpinned: Signed-off-by a third party"             change git commit -q -m "x" -m "Signed-off-by: Cursor Agent <cursoragent@cursor.com>"
expect reject "unpinned: Co-Authored-By still rejected"           change git commit -q -m "x" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
expect reject "unpinned: promo line still rejected"               change git commit -q -m "x" -m "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
expect reject "unpinned: repair refuses without an identity"      sh .githooks/repair main

exit $failed
