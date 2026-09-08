#!/usr/bin/env python3
"""Write the compound-duration golden corpus.

The expected values come from the duration spec, not from the parser, so the
corpus stays an independent oracle.
"""

import json
from pathlib import Path

CASES = {
    "1h30m": 5400,
    "2h5m30s": 7530,
    "0h45m": 2700,
}

TARGET = Path(__file__).resolve().parent.parent / "tests" / "golden" / "cases.json"


def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(CASES, indent=2, sort_keys=True) + "\n")
    print("wrote %s" % TARGET.name)


if __name__ == "__main__":
    main()
