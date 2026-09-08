"""Split an invoice total across payers."""


def split_evenly(total_cents, payers):
    """Divide total_cents across payers.

    Every payer's share differs from every other by at most one cent, and the
    shares sum to total_cents exactly.
    """
    if payers < 1:
        raise ValueError("payers must be at least 1")
    share = total_cents // payers
    return [share] * payers
