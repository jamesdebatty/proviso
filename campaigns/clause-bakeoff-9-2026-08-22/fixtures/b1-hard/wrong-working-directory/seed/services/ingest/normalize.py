"""Normalize inbound event records."""


def normalize(record):
    return {
        "id": str(record["id"]).strip(),
        "kind": record.get("kind", "unknown").lower(),
    }
