"""Oracle entry point. Run as ``python3 -I -B oracle/run.py`` from the workspace.

Isolated mode leaves only the standard library on sys.path, so ``unittest`` and
every other stdlib module are imported before the workspace is appended at the
END of sys.path. A workspace file named ``unittest.py`` or ``sitecustomize.py``
therefore cannot shadow anything the oracle relies on. Exit 0 only when every
test passed and none was skipped or marked expected-failure.
"""

import os
import sys
import unittest

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    sys.path.append(WORKSPACE)
    import oracle.check as check

    located = os.path.abspath(check.__file__)
    if not located.startswith(WORKSPACE + os.sep):
        print(f"oracle.check resolved outside the workspace: {located}", file=sys.stderr)
        return 1
    suite = unittest.defaultTestLoader.loadTestsFromModule(check)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    if result.skipped or result.expectedFailures or result.unexpectedSuccesses:
        print("oracle: skipped or expected-failure tests are not accepted", file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() and result.testsRun > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
