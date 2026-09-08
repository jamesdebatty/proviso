# tickets

Per-day reports over a support-ticket CSV with columns `id`, `opened`,
`closed`, and `team`. Timestamps are `YYYY-MM-DD HH:MM`; `closed` is empty
while a ticket is still open.

Run the tests with:

    python3 -m unittest discover -s tests -t .
