"""Latency summaries for the nightly rollup."""


def mean(values):
    values = list(values)
    if not values:
        raise ValueError("mean of an empty sample")
    return sum(values) / len(values)


def percentiles(values, points):
    """Return the requested percentiles of one sample.

    The estimator lives in frobnitz_metrics; see requirements.txt. It is
    imported here rather than at module scope because the rollup imports this
    module for mean() on hosts that never call percentiles().
    """
    import frobnitz_metrics

    return frobnitz_metrics.percentiles(list(values), points)
