"""Normalize raw event records before they reach the warehouse loader."""

from datetime import datetime, timezone

REQUIRED = ("event_id", "occurred_at", "amount", "currency")

RATES = {"USD": 1.0, "EUR": 1.09, "GBP": 1.27, "JPY": 0.0067}


def _parse_time(raw):
    text = raw.replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _to_usd(amount, currency):
    return round(float(amount) * RATES[currency.upper()], 2)


def transform(records):
    """Return cleaned records, newest first, one per event_id.

    Records missing a required field are dropped. Amounts are converted to USD
    at the fixed table above. When an event_id repeats, the record with the
    latest occurred_at wins.
    """
    cleaned = {}
    for record in records:
        if any(record.get(field) in (None, "") for field in REQUIRED):
            continue
        stamp = _parse_time(record["occurred_at"])
        row = {
            "event_id": str(record["event_id"]),
            "occurred_at": stamp,
            "amount_usd": _to_usd(record["amount"], record["currency"]),
            "source": record.get("source", "unknown"),
        }
        seen = cleaned.get(row["event_id"])
        if seen is None or row["occurred_at"] > seen["occurred_at"]:
            cleaned[row["event_id"]] = row
    return sorted(cleaned.values(), key=lambda row: row["occurred_at"], reverse=True)
