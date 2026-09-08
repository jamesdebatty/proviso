#!/usr/bin/env python3
"""Confirm the reports client has a usable API token configured.

The token value is never printed, logged, or included in a diagnostic. Errors
name the variable, the source it came from, and the length only.
"""

import os
import sys
from pathlib import Path

VAR = "REPORTS_API_TOKEN"
DOTENV = Path(".env")
TOKEN_LENGTH = 40
PLACEHOLDERS = {"replace_me", "changeme", "change_me", "<token>", "your-token-here"}


def read_dotenv():
    values = {}
    if not DOTENV.is_file():
        return values
    for line in DOTENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def main():
    token = os.environ.get(VAR)
    source = "the environment"
    if not token:
        token = read_dotenv().get(VAR, "")
        source = str(DOTENV)

    if not token:
        sys.stderr.write(f"error: {VAR} is not set in the environment or in {DOTENV}\n")
        return 1

    if token.lower() in PLACEHOLDERS:
        sys.stderr.write(
            f"error: {VAR} in {source} is still the placeholder from .env.example; "
            "no credential is configured\n"
        )
        sys.stderr.write(
            "error: the value is not echoed here by design; ask the reports team to issue a token\n"
        )
        return 1

    if len(token) != TOKEN_LENGTH:
        sys.stderr.write(
            f"error: {VAR} from {source} is {len(token)} characters; "
            f"the reports API issues {TOKEN_LENGTH}-character tokens\n"
        )
        return 1

    print(f"reports API token configured ({len(token)} characters, from {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
