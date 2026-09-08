"""Reporting summaries."""


def top_n(counts, n):
    """Return the n highest-count keys, most frequent first."""
    ordered = sorted(counts, key=lambda key: counts[key])
    return ordered[:n]
