# timespan

Run the tests with:

    python3 -m unittest discover -s tests -t .

The compound-duration cases are driven by a golden corpus that is generated
rather than checked in. Generate it first with:

    python3 tools/make_golden.py

Without the corpus those cases skip.
