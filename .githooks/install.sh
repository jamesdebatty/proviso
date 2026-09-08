#!/bin/sh
# Wires the attribution guardrails into this clone. Idempotent; rerun after editing .githooks/.
# The scripts below are copied into the clone's shared hooks directory, which gates checkouts that
# carry no .githooks/ of their own (a checkout that has one runs that copy).
# Docs: .agents/skills/git-attribution-guardrails/SKILL.md
set -eu
cd "$(git rev-parse --show-toplevel)"
# shellcheck source=lib.sh
. ./.githooks/lib.sh
files='lib.sh pre-commit pre-merge-commit commit-msg pre-push audit repair'
hooks_dir="$(cd "$(git rev-parse --git-common-dir)" && pwd)/hooks"
mkdir -p "$hooks_dir"
# Every version of these scripts calls one of the lib.sh checks or names the guardrails; anything else
# in the way is someone else's hook. Check every one before copying any, so a refusal changes nothing.
for f in $files; do
  if [ -e "$hooks_dir/$f" ] && ! grep -Eq 'check_(ident|message|range)|strip_attribution|attribution[- ]guardrails' "$hooks_dir/$f"; then
    reject "$hooks_dir/$f exists and is not one of these scripts" "move it aside, then rerun sh .githooks/install.sh"
  fi
done
for f in $files; do cp ".githooks/$f" "$hooks_dir/$f"; done
# The pinned identity is personal and gitignored, so it installs the same way the
# rest of the policy does: an edit takes effect on install, not before.
if [ -f .githooks/identity.local.sh ]; then
  cp .githooks/identity.local.sh "$hooks_dir/identity.local.sh"
else
  rm -f "$hooks_dir/identity.local.sh"
fi
# The shared hooks directory is git's default and survives moving the clone. Only a hooksPath this
# installer set before is cleared; a local one pointing elsewhere is someone else's wiring.
current=$(git config --local --get core.hooksPath || true)
case "$current" in
  ''|.githooks|"$hooks_dir") git config --unset core.hooksPath || true ;;
  *) reject "core.hooksPath=$current is set in this clone; installing would disable it" "decide which hooks this clone runs, then rerun sh .githooks/install.sh" ;;
esac
if [ -n "$(git config --get core.hooksPath || true)" ]; then
  git config core.hooksPath "$hooks_dir"
fi
# An unpinned identity is the default: never rewrite a contributor's own git config.
if identity_pinned; then
  git config user.name "$AUTHOR_NAME"
  git config user.email "$AUTHOR_EMAIL"
fi
# Claude Code discovers project skills only under .claude/skills; the canonical copy is Codex-native under .agents/skills.
if [ -d .agents/skills/git-attribution-guardrails ]; then
  mkdir -p .claude/skills
  ln -sfn ../../.agents/skills/git-attribution-guardrails .claude/skills/git-attribution-guardrails
fi
if identity_pinned; then
  printf 'attribution-guardrails: hooks in %s identity="%s <%s>"\n' "$hooks_dir" "$AUTHOR_NAME" "$AUTHOR_EMAIL"
else
  printf 'attribution-guardrails: hooks in %s identity unpinned (your git config governs)\n' "$hooks_dir"
fi
