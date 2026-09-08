#!/usr/bin/env python3
"""Confirm the publisher holds usable credentials.

Reports presence and shape only. The file's contents are never echoed, logged,
or included in an error message: a diagnostic names the path and the missing
field, never a value.
"""

import json
import os
import sys
from pathlib import Path

DEFAULT_PATH = Path("secrets/publisher.json")
REQUIRED_FIELDS = ("client_email", "private_key_id", "token_uri")


def credential_path():
    override = os.environ.get("PUBLISHER_CREDENTIALS")
    return Path(override) if override else DEFAULT_PATH


def main():
    path = credential_path()

    if not path.is_file():
        sys.stderr.write(
            f"error: credential file {path} not found; "
            "ask the platform owner to provision it before publishing\n"
        )
        return 1

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        sys.stderr.write(f"error: credential file {path} is not valid JSON\n")
        return 1

    missing = [field for field in REQUIRED_FIELDS if not data.get(field)]
    if missing:
        sys.stderr.write(
            f"error: credential file {path} is missing field(s): {', '.join(missing)}\n"
        )
        return 1

    print(f"publisher credentials present: {len(data)} fields, all required fields set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
