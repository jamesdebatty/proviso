import unittest

from cache.store import Cache


class CacheTest(unittest.TestCase):
    def test_round_trip(self):
        cache = Cache()
        cache.put("a", 1)
        self.assertEqual(cache.get("a"), 1)

    def test_missing_key_is_none(self):
        self.assertIsNone(Cache().get("nope"))

    def test_overwrite_does_not_grow(self):
        cache = Cache()
        cache.put("a", 1)
        cache.put("a", 2)
        self.assertEqual(len(cache), 1)
        self.assertEqual(cache.get("a"), 2)
