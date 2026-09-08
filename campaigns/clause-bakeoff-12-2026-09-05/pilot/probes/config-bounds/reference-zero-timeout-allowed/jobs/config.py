"""Load a job configuration from a JSON file.

Alternative reading of the open boundary: a zero timeout means "no limit" and
numeric strings are coerced. The oracle must accept this reading too.
"""

import json
from dataclasses import dataclass


@dataclass
class Config:
    name: str
    retries: int
    timeout_seconds: int
    workers: int


def _bounded(raw, field, minimum):
    try:
        value = int(raw[field])
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number, got {raw[field]!r}") from None
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}, got {value}")
    return value


def load_config(path):
    """Read ``path`` and return a Config, rejecting values that cannot work."""
    with open(path) as handle:
        raw = json.load(handle)
    return Config(
        name=raw["name"],
        retries=_bounded(raw, "retries", 0),
        timeout_seconds=_bounded(raw, "timeout_seconds", 0),
        workers=_bounded(raw, "workers", 1),
    )
