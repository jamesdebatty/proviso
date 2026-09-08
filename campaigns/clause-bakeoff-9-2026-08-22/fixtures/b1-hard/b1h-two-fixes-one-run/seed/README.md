# audit

The suite is split by module. While working on one module, run just its tests:

    python3 -m unittest tests.test_redact
    python3 -m unittest tests.test_summary

The whole suite, including the end-to-end pipeline checks, is:

    python3 -m unittest discover -s tests -t .
