#!/bin/sh
# Shared policy for the attribution guardrails; sourced by every hook here.
# Docs: .agents/skills/git-attribution-guardrails/SKILL.md

# CDPATH would make cd print the directory into the path computations below.
unset CDPATH

SKILL_DOC='.agents/skills/git-attribution-guardrails/SKILL.md'
# Directory of the running script: .githooks/ from the checkout, the hooks directory once installed.
HOOKS_DIR=$(cd "$(dirname "$0")" && pwd)

# The identity every commit here carries as author and committer. Both are empty
# by default, which leaves your own git config in charge: install.sh will not
# touch user.name or user.email, and the identity checks below stand down. The
# attribution rules always apply — they are about the project, not about who
# maintains it.
#
# To pin an identity, put your values in .githooks/identity.local.sh. That file
# is gitignored, and install.sh copies it next to the installed hooks so the
# installed hooks can see it too. Note it is not gated the way tracked policy is:
# `defer_to_checkout` compares tracked files against HEAD and cannot see an
# untracked one, so editing the checkout's copy takes effect immediately. That is
# the point — it is your own clone's identity, not repository policy.
AUTHOR_NAME=''
AUTHOR_EMAIL=''
if [ -f "$HOOKS_DIR/identity.local.sh" ]; then
  # shellcheck source=/dev/null
  . "$HOOKS_DIR/identity.local.sh"
fi

# identity_pinned: an identity is configured, so the identity checks have something to enforce.
identity_pinned() { [ -n "$AUTHOR_NAME" ] && [ -n "$AUTHOR_EMAIL" ]; }

# exempt_email: the address a trailer may name without counting as third-party
# credit. Pinned, that is the pinned address. Unpinned, it is the committer's
# own, so a contributor can sign off their own work; with no address at all,
# every identity-bearing trailer is third-party.
exempt_email() {
  if [ -n "$AUTHOR_EMAIL" ]; then
    printf '%s' "$AUTHOR_EMAIL"
    return
  fi
  committer=$(git var GIT_COMMITTER_IDENT 2>/dev/null) || return 0
  case $committer in
    *'<'*'>'*) committer=${committer#*<}; printf '%s' "${committer%%>*}" ;;
  esac
}

# Matched against the lower-cased line: trailer keys that attribute authorship to anyone.
TRAILER_KEYS_RE='^[[:space:]]*(co-authored-by|co-developed-by|assisted-by|generated-by|generated-with)[[:space:]]*:'
# Matched against the lower-cased line: the tool promo line ("Generated with [Claude Code](...)").
PROMO_RE='generated with .?claude code'
# Any "Key: Name <email>" trailer; its email must be AUTHOR_EMAIL.
TRAILER_EMAIL_RE='^[[:space:]]*[A-Za-z][A-Za-z-]*:[[:space:]]*[^<]*<[^>@]+@[^>]+>'

reject() {
  printf 'attribution-guardrails: REJECTED %s\n' "$1" >&2
  printf 'attribution-guardrails: fix: %s\n' "$2" >&2
  printf 'attribution-guardrails: see %s (on main)\n' "$SKILL_DOC" >&2
  exit 1
}

# check_ident AUTHOR|COMMITTER: the identity git is about to write equals the hardcoded one.
check_ident() {
  identity_pinned || return 0
  ident=$(git var "GIT_${1}_IDENT") || exit 1
  name=${ident%% <*}
  email=${ident#*<}
  email=${email%%>*}
  if [ "$name" != "$AUTHOR_NAME" ] || [ "$email" != "$AUTHOR_EMAIL" ]; then
    reject "$1 is \"$name <$email>\"; commits here carry \"$AUTHOR_NAME <$AUTHOR_EMAIL>\"" \
      'drop --author, -c user.*, and GIT_AUTHOR_*/GIT_COMMITTER_* overrides; run sh .githooks/install.sh; for an amend add --reset-author'
  fi
}

# defer_to_checkout HOOK-ARGS...: when the checkout carries .githooks/ and it matches HEAD, its copy of
# this hook runs instead of the installed one; otherwise the copies install.sh last put in place run.
# A change to .githooks/ is therefore gated by the previous policy and takes effect from the next commit.
# GUARDRAILS_DEFERRED bounds this to one exec and is cleared so nested git commands start fresh.
defer_to_checkout() {
  if [ -n "${GUARDRAILS_DEFERRED:-}" ]; then
    unset GUARDRAILS_DEFERRED
    return
  fi
  script=$(basename "$0")
  if [ -f ".githooks/$script" ] && [ "$HOOKS_DIR" != "$(cd .githooks && pwd)" ] \
    && git ls-files --error-unmatch ".githooks/$script" >/dev/null 2>&1 \
    && git diff --quiet HEAD -- .githooks 2>/dev/null; then
    GUARDRAILS_DEFERRED=1
    export GUARDRAILS_DEFERRED
    exec sh ".githooks/$script" "$@"
  fi
}

# message_body FILE: the lines git will keep, i.e. nothing after the scissors line and no comment lines.
message_body() {
  cc=$(git config --get core.commentString || git config --get core.commentChar || printf '#')
  [ "$cc" = auto ] && cc='#'
  awk -v cc="$cc" '
    index($0, cc) == 1 && substr($0, length(cc) + 1) ~ /^ -+ >8 -+$/ { exit }
    index($0, cc) != 1 { print }
  ' "$1"
}

# attribution_scan bad|clean: stdin is a message; "bad" prints its third-party attribution lines, "clean" prints everything else.
attribution_scan() {
  awk -v mode="$1" -v keys_re="$TRAILER_KEYS_RE" -v promo_re="$PROMO_RE" -v trailer_re="$TRAILER_EMAIL_RE" -v ok_email="$(exempt_email)" '
    {
      l = tolower($0)
      bad = (l ~ keys_re || l ~ promo_re)
      if (!bad && $0 ~ trailer_re && match($0, /<[^>@]+@[^>]+>/))
        bad = (substr($0, RSTART + 1, RLENGTH - 2) != ok_email)
      if (bad != (mode == "bad")) next
      if (mode == "clean") {
        if ($0 ~ /^[[:space:]]*$/) { pending++; next }
        for (; pending > 0; pending--) print ""
      }
      print
    }'
}
attribution_lines() { attribution_scan bad; }
strip_attribution() { attribution_scan clean; }

# check_message FILE: the proposed message names no third party.
check_message() {
  bad=$(message_body "$1" | attribution_lines)
  [ -z "$bad" ] || reject "the message attributes the commit to a third party:
$bad" 'delete that line; a message here ends at the last line of its body, with no attribution trailer or "Generated with" line'
}

# check_range REV-LIST-ARGS...: every commit git rev-list selects carries the hardcoded identity and no attribution line.
check_range() {
  expected="$AUTHOR_NAME <$AUTHOR_EMAIL>"
  for c in $(git rev-list "$@"); do
    if identity_pinned; then
      an=$(git log -1 --format='%an <%ae>' "$c")
      cn=$(git log -1 --format='%cn <%ce>' "$c")
      [ "$an" = "$expected" ] || reject "commit $c author is \"$an\"" "rewrite the branch: $HOOKS_DIR/repair <base>"
      [ "$cn" = "$expected" ] || reject "commit $c committer is \"$cn\"" "rewrite the branch: $HOOKS_DIR/repair <base>"
    fi
    bad=$(git log -1 --format=%B "$c" | attribution_lines)
    [ -z "$bad" ] || reject "commit $c attributes to a third party: $bad" "rewrite the branch: $HOOKS_DIR/repair <base>"
  done
}
