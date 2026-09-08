#!/usr/bin/env python3
"""Confirm the export job can authenticate against the staging API."""

import os
import sys

TOKEN_VAR = "EXPORT_API_TOKEN"


def main():
    token = os.environ.get(TOKEN_VAR)
    if not token:
        sys.stderr.write(f"error: {TOKEN_VAR} is not set; cannot authenticate\n")
        return 1
    if len(token) < 32:
        sys.stderr.write(f"error: {TOKEN_VAR} is malformed\n")
        return 1
    sys.stdout.write("staging authentication ok\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
