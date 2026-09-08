#!/usr/bin/env python3
"""Build check: every module parses and every schema file is valid."""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SCHEMA_KEYS = ("name", "version", "fields")


def main():
    problems = []
    for source in sorted(ROOT.glob("manifest/*.py")):
        try:
            ast.parse(source.read_text(), filename=str(source))
        except SyntaxError as exc:
            problems.append("%s: %s" % (source.name, exc))
    for schema in sorted(ROOT.glob("schemas/*.json")):
        try:
            loaded = json.loads(schema.read_text())
        except json.JSONDecodeError as exc:
            problems.append("%s: %s" % (schema.name, exc))
            continue
        missing = [key for key in REQUIRED_SCHEMA_KEYS if key not in loaded]
        if missing:
            problems.append("%s: missing %s" % (schema.name, ", ".join(missing)))
    for problem in problems:
        print("FAIL %s" % problem)
    if problems:
        return 1
    print("build ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
