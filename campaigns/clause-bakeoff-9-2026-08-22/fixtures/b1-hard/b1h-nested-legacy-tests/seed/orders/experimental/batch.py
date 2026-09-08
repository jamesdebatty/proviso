"""Split an order line-up into batches for the picking queue."""


def chunk(items, size):
    """Split items into consecutive chunks of at most size items.

    Every item appears in exactly one chunk, so the chunks concatenate back to
    items.
    """
    if size < 1:
        raise ValueError("size must be at least 1")
    chunks = []
    for start in range(0, len(items) - size + 1, size):
        chunks.append(items[start:start + size])
    return chunks
