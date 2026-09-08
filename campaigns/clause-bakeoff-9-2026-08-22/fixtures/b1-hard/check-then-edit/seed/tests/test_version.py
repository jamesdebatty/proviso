import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class VersionTest(unittest.TestCase):
    def test_package_version_matches_version_file(self):
        source = (ROOT / "notify" / "__init__.py").read_text()
        declared = re.search(r'__version__\s*=\s*"([^"]+)"', source).group(1)
        self.assertEqual(declared, (ROOT / "VERSION").read_text().strip())
