"""Parse compact duration strings such as '90s', '45m' or '1h30m'."""

_UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    """Return the number of seconds described by text.

    Every unit present in the string contributes to the total, so '1h30m' is
    5400 seconds.
    """
    for unit, factor in _UNITS.items():
        index = text.find(unit)
        if index != -1:
            return int(text[:index]) * factor
    raise ValueError("unparsable duration: %s" % text)
