import unittest

from manifest.merge import deep_merge


class DeepMergeTest(unittest.TestCase):
    def test_adds_new_key(self):
        self.assertEqual(deep_merge({"a": 1}, {"b": 2}), {"a": 1, "b": 2})

    def test_override_replaces_scalar(self):
        self.assertEqual(deep_merge({"a": 1}, {"a": 2}), {"a": 2})

    def test_base_is_not_mutated(self):
        base = {"limits": {"cpu": "500m"}}
        deep_merge(base, {"limits": {"memory": "256Mi"}})
        self.assertEqual(base, {"limits": {"cpu": "500m"}})


class NestedMergeTest(unittest.TestCase):
    def test_nested_keys_are_kept(self):
        merged = deep_merge(
            {"limits": {"cpu": "500m", "memory": "256Mi"}},
            {"limits": {"memory": "512Mi"}},
        )
        self.assertEqual(merged, {"limits": {"cpu": "500m", "memory": "512Mi"}})

    def test_deeply_nested_keys_are_kept(self):
        merged = deep_merge(
            {"spec": {"limits": {"cpu": "500m"}, "replicas": 2}},
            {"spec": {"limits": {"memory": "512Mi"}}},
        )
        self.assertEqual(
            merged,
            {"spec": {"limits": {"cpu": "500m", "memory": "512Mi"}, "replicas": 2}},
        )
