"""Load a job configuration from a JSON file."""

import json
from dataclasses import dataclass


@dataclass
class Config:
    name: str
    retries: int
    timeout_seconds: int
    workers: int


def load_config(path):
    """Read ``path`` and return a Config."""
    with open(path) as handle:
        raw = json.load(handle)
    return Config(
        name=raw["name"],
        retries=raw["retries"],
        timeout_seconds=raw["timeout_seconds"],
        workers=raw["workers"],
    )
