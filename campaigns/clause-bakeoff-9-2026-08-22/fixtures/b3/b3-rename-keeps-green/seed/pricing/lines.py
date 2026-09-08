"""Line-item arithmetic."""


def calc(quantity, unit_price, discount=0.0):
    """Total for one line: quantity x unit price, less a fractional discount."""
    return round(quantity * unit_price * (1.0 - discount), 2)
