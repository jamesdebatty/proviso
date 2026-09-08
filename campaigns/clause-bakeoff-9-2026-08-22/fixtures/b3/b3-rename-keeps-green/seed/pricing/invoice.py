"""Invoice totals."""

from pricing.lines import calc


def invoice_total(lines):
    """Sum calc() over a list of (quantity, unit_price, discount) tuples."""
    return round(sum(calc(*line) for line in lines), 2)
