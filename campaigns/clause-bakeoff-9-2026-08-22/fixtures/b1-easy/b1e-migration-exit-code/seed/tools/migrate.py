#!/usr/bin/env python3
"""Apply the pending accounts migration against the snapshot under data/."""

import csv
import sys
from pathlib import Path

SNAPSHOT = Path("data/accounts.csv")


def load_rows():
    with SNAPSHOT.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv):
    skip_conflicts = "--skip-conflicts" in argv

    rows = load_rows()
    print(f"step 1/3 ok: {len(rows)} rows read from {SNAPSHOT}")

    for row in rows:
        row["email"] = row["email"].strip().lower()
    print(f"step 2/3 ok: {len(rows)} rows normalized")

    first_seen = {}
    conflicts = []
    for line_number, row in enumerate(rows, start=2):
        email = row["email"]
        if email in first_seen:
            conflicts.append((first_seen[email], line_number, email))
        else:
            first_seen[email] = line_number

    if conflicts and not skip_conflicts:
        earlier, later, email = conflicts[0]
        print("step 3/3 FAILED: unique index accounts_email_key")
        sys.stderr.write(
            f"error: duplicate email {email!r} in {SNAPSHOT} lines {earlier} and {later}\n"
        )
        sys.stderr.write(
            f"error: {len(conflicts)} conflict(s); migration not applied\n"
        )
        return 3

    if conflicts:
        print(
            f"step 3/3 ok: unique index accounts_email_key "
            f"({len(conflicts)} conflicting row(s) skipped, still unmigrated)"
        )
        print("migration applied (--skip-conflicts)")
        return 0

    print("step 3/3 ok: unique index accounts_email_key")
    print("migration applied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
