#!/usr/bin/env python3
"""Verify the release bundle against the signed checksum list."""

import hashlib
import sys
from pathlib import Path

CHECKSUMS = Path("checksums.txt")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entries():
    out = []
    for line in CHECKSUMS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        recorded, name = line.split(None, 1)
        out.append((recorded, name.strip()))
    return out


def main(argv):
    listed = entries()

    if "--update" in argv:
        body = "".join(f"{digest(Path(name))}  {name}\n" for _, name in listed)
        CHECKSUMS.write_text(body)
        print(f"rewrote {CHECKSUMS} from the bundle on disk ({len(listed)} entries)")
        return 0

    bad = 0
    for recorded, name in listed:
        path = Path(name)
        if not path.exists():
            print(f"MISSING {name}")
            bad += 1
            continue
        if digest(path) == recorded:
            print(f"OK      {name}")
        else:
            print(f"FAILED  {name}")
            sys.stderr.write(f"error: {name} does not match the signed checksum\n")
            bad += 1

    if bad:
        sys.stderr.write(
            f"error: {bad} of {len(listed)} bundle file(s) failed verification; do not publish\n"
        )
        return 1

    print("release bundle verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
