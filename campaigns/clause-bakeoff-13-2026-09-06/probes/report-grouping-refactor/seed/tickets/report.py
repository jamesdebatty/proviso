"""Per-day reports over ticket rows."""

import csv
from datetime import datetime

STAMP = "%Y-%m-%d %H:%M"


def load_rows(path):
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def opened_per_day(rows):
    """Return (day, count) pairs of tickets opened, oldest day first."""
    counts = {}
    for row in rows:
        stamp = row["opened"].strip()
        if not stamp:
            continue
        day = datetime.strptime(stamp, STAMP).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return sorted(counts.items())


def closed_per_day(rows):
    """Return (day, count) pairs of tickets closed, oldest day first."""
    counts = {}
    for row in rows:
        stamp = row["closed"].strip()
        if not stamp:
            continue
        day = datetime.strptime(stamp, STAMP).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return sorted(counts.items())


def backlog_per_day(rows):
    """Return (day, still_open) pairs: tickets open at the end of each day."""
    opened = {}
    for row in rows:
        stamp = row["opened"].strip()
        if not stamp:
            continue
        day = datetime.strptime(stamp, STAMP).date().isoformat()
        opened[day] = opened.get(day, 0) + 1
    closed = {}
    for row in rows:
        stamp = row["closed"].strip()
        if not stamp:
            continue
        day = datetime.strptime(stamp, STAMP).date().isoformat()
        closed[day] = closed.get(day, 0) + 1
    out = []
    running = 0
    for day in sorted(set(opened) | set(closed)):
        running += opened.get(day, 0) - closed.get(day, 0)
        out.append((day, running))
    return out
