"""Per-day reports over ticket rows."""

import csv
from datetime import datetime

STAMP = "%Y-%m-%d %H:%M"


def load_rows(path):
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle))


def group_by_day(rows, column):
    """Return a dict of ISO day -> number of rows whose ``column`` falls on it.

    Rows with an empty value in ``column`` are skipped.
    """
    counts = {}
    for row in rows:
        stamp = row[column].strip()
        if not stamp:
            continue
        day = datetime.strptime(stamp, STAMP).date().isoformat()
        counts[day] = counts.get(day, 0) + 1
    return counts


def opened_per_day(rows):
    """Return (day, count) pairs of tickets opened, oldest day first."""
    return sorted(group_by_day(rows, "opened").items())


def closed_per_day(rows):
    """Return (day, count) pairs of tickets closed, oldest day first."""
    return sorted(group_by_day(rows, "closed").items())


def backlog_per_day(rows):
    """Return (day, still_open) pairs: tickets open at the end of each day."""
    opened = group_by_day(rows, "opened")
    closed = group_by_day(rows, "closed")
    out = []
    running = 0
    for day in sorted(set(opened) | set(closed)):
        running += opened.get(day, 0) - closed.get(day, 0)
        out.append((day, running))
    return out
