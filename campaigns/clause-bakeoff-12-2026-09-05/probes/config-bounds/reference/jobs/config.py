"""Load a job configuration from a JSON file."""

import json
from dataclasses import dataclass


@dataclass
class Config:
    name: str
    retries: int
    timeout_seconds: int
    workers: int


def _whole_number(raw, field, minimum):
    value = raw[field]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a whole number, got {value!r}")
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}, got {value}")
    return value


def load_config(path):
    """Read ``path`` and return a Config.

    Raises ValueError naming the field when retries is negative, timeout_seconds
    is not positive, or workers is below one.
    """
    with open(path) as handle:
        raw = json.load(handle)
    return Config(
        name=raw["name"],
        retries=_whole_number(raw, "retries", 0),
        timeout_seconds=_whole_number(raw, "timeout_seconds", 1),
        workers=_whole_number(raw, "workers", 1),
    )
