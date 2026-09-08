import sys
from datetime import date

from recur.monthly import next_monthly


def main(argv):
    if len(argv) != 1:
        print("usage: python3 -m recur YYYY-MM-DD", file=sys.stderr)
        return 2
    print(next_monthly(date.fromisoformat(argv[0])).isoformat())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
