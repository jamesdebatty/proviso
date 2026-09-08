#!/bin/zsh
set -u
LABEL="$1"; BIN="$2"; MODEL="$3"; CWD="$4"; MODE="$5"; SPFILE="${6:-}"
OUT="/tmp/ccap9/raw-$LABEL.json"; rm -f "$OUT"
python3 /tmp/ccap9/server.py "$OUT" > /tmp/ccap9/port-$LABEL.txt 2>/dev/null &
SRV=$!
for i in {1..50}; do PORT=$(cat /tmp/ccap9/port-$LABEL.txt 2>/dev/null); [ -n "$PORT" ] && break; sleep 0.1; done
[ -z "${PORT:-}" ] && { echo "no port"; kill $SRV 2>/dev/null; exit 1; }
CAP_CWD="$CWD" CAP_BIN="$BIN" CAP_MODEL="$MODEL" CAP_PORT="$PORT" CAP_MODE="$MODE" CAP_SPFILE="$SPFILE" CAP_TOOLS="${CAP_TOOLS:-}" CAP_DISALLOW="${CAP_DISALLOW:-}" \
  node /tmp/ccap9/drive2.mjs >/tmp/ccap9/drv-$LABEL.log 2>&1
wait $SRV 2>/dev/null
if [ -s "$OUT" ]; then echo "[$LABEL] CAPTURED $(wc -c < "$OUT") bytes"; else echo "[$LABEL] NO CAPTURE"; tail -3 /tmp/ccap9/drv-$LABEL.log; fi
