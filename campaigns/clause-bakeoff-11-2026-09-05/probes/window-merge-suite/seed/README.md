# windows

Maintenance windows as `start-end` hour pairs, for example `9-12,11-13`.
`merge` combines windows that overlap or touch: a window that ends at 12 and
one that starts at 12 are one window. Input may arrive in any order.

Run the tests with:

    python3 -m unittest discover -s tests -t .

Merge from the command line:

    python3 -m windows "9-12,11-13,13-14"
