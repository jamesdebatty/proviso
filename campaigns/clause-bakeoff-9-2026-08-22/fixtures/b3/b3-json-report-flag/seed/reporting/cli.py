"""Summarize a file of numbers."""

import argparse
import sys


def summarize(values):
    """Return total, mean and max for a non-empty list of numbers."""
    return {
        "total": sum(values),
        "mean": sum(values) / len(values),
        "max": max(values),
    }


def read_values(path):
    with open(path) as handle:
        return [float(line) for line in handle if line.strip()]


def main(argv=None, stream=sys.stdout):
    parser = argparse.ArgumentParser(prog="report")
    parser.add_argument("path")
    args = parser.parse_args(argv)
    summary = summarize(read_values(args.path))
    print(
        "total={total:.2f} mean={mean:.2f} max={max:.2f}".format(**summary),
        file=stream,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
