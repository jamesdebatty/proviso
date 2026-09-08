"""Hourly rollup of event timestamps."""

from datetime import timedelta


def bucket(ts):
    """Return the hour nearest to ``ts``.

    Half past rounds up: 10:29:59 -> 10:00, 10:30:00 -> 11:00.
    """
    shifted = ts + timedelta(minutes=30)
    return shifted.replace(minute=0, second=0, microsecond=0)


def count_by_bucket(events):
    """Return a dict of bucket -> number of events, from a list of datetimes."""
    counts = {}
    for ts in events:
        hour = bucket(ts)
        counts[hour] = counts.get(hour, 0) + 1
    return counts


def render(counts):
    """Return one line per bucket, oldest first: ``YYYY-MM-DD HH:MM  n``."""
    lines = []
    for hour in sorted(counts):
        lines.append(f"{hour:%Y-%m-%d %H:%M}  {counts[hour]}")
    return "\n".join(lines)
