"""Daily rollup report."""

import frobnitz_config


def load_thresholds(path):
    return frobnitz_config.load(path)["thresholds"]


def rollup(rows, thresholds):
    total = sum(row["amount"] for row in rows)
    return {"total": total, "over": total > thresholds["daily"]}
