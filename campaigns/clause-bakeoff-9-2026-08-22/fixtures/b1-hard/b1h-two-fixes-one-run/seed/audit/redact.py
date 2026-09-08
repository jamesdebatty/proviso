"""Mask secret-looking tokens in a log line."""

import re

SECRET = re.compile(r"sk-[A-Za-z0-9]{4,}")


def redact(line):
    """Return line with every secret-looking token replaced by [REDACTED]."""
    match = SECRET.search(line)
    if match is None:
        return line
    return line.replace(match.group(0), "[REDACTED]")
