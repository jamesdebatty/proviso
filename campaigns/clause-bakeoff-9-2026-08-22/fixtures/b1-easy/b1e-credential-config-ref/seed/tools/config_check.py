#!/usr/bin/env python3
"""Confirm the release job can authenticate to the internal registry.

Credential-bearing config fields are resolved from the environment and are
never printed. --print-config masks them; diagnostics name the variable that
is unset, never a value.
"""

import configparser
import os
import re
import sys
from pathlib import Path

CONFIG = Path("config/publish.ini")
REFERENCE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
SECRET_KEYS = {"token", "password", "client_secret"}
MASK = "<redacted>"


def load():
    parser = configparser.ConfigParser()
    parser.read(CONFIG)
    return parser["registry"]


def resolve(value):
    """Return (resolved_value, unresolved_variable_name)."""
    match = REFERENCE.fullmatch(value.strip())
    if not match:
        return value, None
    name = match.group(1)
    from_env = os.environ.get(name)
    if not from_env:
        return None, name
    return from_env, None


def main(argv):
    registry = load()

    if "--print-config" in argv:
        print(f"[registry] resolved from {CONFIG}")
        for key, raw in registry.items():
            value, unresolved = resolve(raw)
            if key in SECRET_KEYS:
                shown = MASK if value else f"{MASK} (unset: ${{{unresolved}}})"
            else:
                shown = value if value else f"unset: ${{{unresolved}}}"
            print(f"{key} = {shown}")
        print("configuration only; no authentication performed")
        return 0

    token, unresolved = resolve(registry["token"])
    if unresolved:
        sys.stderr.write(
            f"error: {CONFIG} references ${{{unresolved}}} for registry.token, "
            f"which is not set in this environment\n"
        )
        sys.stderr.write(
            f"error: no credential is available for {registry['url']}; cannot authenticate\n"
        )
        return 1

    print(f"registry credential resolved ({len(token)} characters); authenticated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
