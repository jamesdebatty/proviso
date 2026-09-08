# recur

Monthly billing recurrence. `next_monthly(d)` returns the date of the next
monthly charge after `d`; `schedule(start, n)` returns the next `n` dates.

Run the tests with:

    python3 -m unittest discover -s tests -t .

Print the next charge date from the command line:

    python3 -m recur 2025-01-15
