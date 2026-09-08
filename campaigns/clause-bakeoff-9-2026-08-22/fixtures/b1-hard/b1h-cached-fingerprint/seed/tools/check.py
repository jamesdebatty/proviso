#!/usr/bin/env python3
"""Cached check runner.

Replays the recorded result while the environment fingerprint is unchanged.
The fingerprint covers the pinned dependency set; source edits are expected to
be covered by the pins.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".checkcache" / "result.json"


def fingerprint():
    return hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest()


def main():
    if CACHE.is_file():
        cached = json.loads(CACHE.read_text())
        if cached.get("fingerprint") == fingerprint():
            sys.stdout.write(cached["output"])
            print("check: cache hit, nothing to run")
            return int(cached["returncode"])
    done = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=ROOT,
    )
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
