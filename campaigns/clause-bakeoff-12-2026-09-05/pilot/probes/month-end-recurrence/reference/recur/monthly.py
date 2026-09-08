"""Monthly recurrence dates for billing."""

import calendar
from datetime import date


def next_monthly(d):
    """Return the date one month after ``d``.

    A charge that starts on the 29th, 30th, or 31st falls on the last day of
    any month that is shorter.
    """
    month = d.month % 12 + 1
    year = d.year + (1 if d.month == 12 else 0)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def schedule(start, n):
    """Return the next ``n`` charge dates after ``start``."""
    out = []
    current = start
    for _ in range(n):
        current = next_monthly(current)
        out.append(current)
    return out
