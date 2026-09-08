"""Convert local wall-clock minutes to UTC."""


def to_utc(local_minutes, offset_minutes):
    """Convert a local time-of-day in minutes to UTC minutes.

    offset_minutes is the zone's offset east of UTC, so UTC-0700 is -420.
    The result wraps within a 1440-minute day.
    """
    return (local_minutes + offset_minutes) % 1440
