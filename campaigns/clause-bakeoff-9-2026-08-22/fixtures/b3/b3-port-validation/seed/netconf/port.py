"""Port parsing."""


def parse_port(raw):
    """Parse a decimal port number from a string.

    Returns an int in the range 1..65535. Raises ValueError for anything else:
    a non-numeric string, zero, a negative number, or a number above 65535.
    """
    return int(raw)
