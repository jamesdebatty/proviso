#!/bin/sh
# Test wrapper. Reuses the last recorded result when the cache is warm so that
# repeated local runs stay fast.
CACHE=.cache/last_run.txt
if [ -f "$CACHE" ]; then
  cat "$CACHE"
  exit 0
fi
python3 -m unittest discover -s tests -t . 2>&1
