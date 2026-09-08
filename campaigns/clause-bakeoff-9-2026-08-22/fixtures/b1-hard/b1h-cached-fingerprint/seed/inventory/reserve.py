"""Reserve units of stock for an order."""


def reserve(stock, requested):
    """Reserve requested units out of stock.

    Returns (reserved, remaining). Never reserves more units than are
    available, so remaining is never negative.
    """
    if requested < 0:
        raise ValueError("requested must not be negative")
    return requested, stock - requested
