"""Merge maintenance windows given as (start, end) hour pairs."""


def merge(intervals):
    """Return the windows with overlapping or touching ones combined, in order."""
    merged = []
    for start, end in intervals:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
