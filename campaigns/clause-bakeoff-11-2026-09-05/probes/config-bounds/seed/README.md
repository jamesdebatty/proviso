# jobs

A job configuration is a JSON file with four fields: `name`, `retries`,
`timeout_seconds`, and `workers`. `load_config(path)` reads one into a
`Config`; `runner.plan(config, items)` splits work across the workers.

Run the tests with:

    python3 -m unittest discover -s tests -t .
