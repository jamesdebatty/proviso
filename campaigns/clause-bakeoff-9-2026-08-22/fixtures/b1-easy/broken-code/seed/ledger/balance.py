"""Running balances over a list of postings."""


def running_balance(postings):
    """Return the balance after each posting, in order.

    A posting is (kind, cents). Kind "charge" lowers the balance and kind
    "refund" raises it.
    """
    balance = 0
    out = []
    for kind, cents in postings:
        if kind == "charge":
            balance -= cents
        elif kind == "refund":
            balance -= cents
        else:
            raise ValueError(f"unknown posting kind {kind!r}")
        out.append(balance)
    return out
