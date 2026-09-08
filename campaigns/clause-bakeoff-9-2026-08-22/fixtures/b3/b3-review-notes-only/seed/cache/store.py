"""A tiny in-process cache."""


class Cache:
    """Keys to values, with no bound on size."""

    def __init__(self):
        self._items = {}

    def get(self, key):
        return self._items.get(key)

    def put(self, key, value):
        self._items[key] = value

    def __len__(self):
        return len(self._items)
