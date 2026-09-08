#!/bin/bash
# Self-driving supervisor for bakeoff 8: carries the campaign from partial
# generation through judging without needing an agent session alive.
#
# Detached (nohup) so it survives host-session restarts, which have repeatedly
# orphaned in-session watchers. Idempotent: it only launches work that is not
# already running, and every underlying step resumes losslessly from
# hash-validated caches.
#
# Usage: nohup ./supervise.sh <out-dir> >> <out-dir>/supervisor.log 2>&1 &

set -u
OUT="$1"
CAMPAIGN="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$CAMPAIGN/../.." && pwd)"
PINS="$HOME/.claude-eval-pins/bakeoff8"
CLAUDE_VERSION="2.1.232 (Claude Code)"
TARGET=75
MAX_MINUTES=240

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

responses() { ls "$OUT/responses" 2>/dev/null | grep -cv failed; }

for ((minute = 0; minute < MAX_MINUTES; minute++)); do
    if [ -f "$OUT/bakeoff-results.json" ]; then
        log "results present; supervisor done"
        exit 0
    fi

    count=$(responses)

    if [ "$count" -lt "$TARGET" ]; then
        if ! pgrep -f "promptfoo.*clause-bakeoff-8" > /dev/null &&
           ! pgrep -f "promptfooconfig.yaml" > /dev/null; then
            log "generation stalled at $count/$TARGET — relaunching"
            cd "$CAMPAIGN" || exit 1
            PATH="$PINS:$PATH" \
            BAKEOFF8_CLAUDE_VERSION="$CLAUDE_VERSION" \
            BAKEOFF8_OUT_DIR="$OUT" \
            PROMPTFOO_PYTHON=/opt/homebrew/bin/python3 \
            npx promptfoo@latest eval -c promptfooconfig.yaml \
                --repeat 5 -j 1 --no-cache --no-share \
                >> "$OUT/generation.log" 2>&1
            log "generation pass exited $? at $(responses)/$TARGET"
        fi
    else
        if ! pgrep -f "clause-bakeoff-8-2026-08-11/analyze.py" > /dev/null; then
            log "all $TARGET responses present — launching judging"
            cd "$PROJECT" || exit 1
            PATH="$PINS:$PATH" python3 \
                campaigns/clause-bakeoff-8-2026-08-11/analyze.py \
                --out-dir "$OUT" --execute >> "$OUT/judging.log" 2>&1
            status=$?
            log "judging pass exited $status"
            if [ -f "$OUT/bakeoff-results.json" ]; then
                log "results written; supervisor done"
                exit 0
            fi
            [ "$status" -ne 0 ] && log "judging failed; will retry after backoff" && sleep 120
        fi
    fi

    sleep 60
done

log "supervisor hit the ${MAX_MINUTES}-minute ceiling; stopping"
exit 1
