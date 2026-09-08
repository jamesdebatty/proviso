#!/bin/sh
# Integration job. Integration tests are named *_test.py so the default unit
# discovery pattern leaves them alone.
cd "$(dirname "$0")/.." || exit 1
python3 -m unittest discover -s tests/integration -t . -p '*_test.py'
