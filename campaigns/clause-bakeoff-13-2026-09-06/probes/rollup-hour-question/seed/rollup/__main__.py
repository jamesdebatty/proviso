import sys
from datetime import datetime

from rollup.hourly import count_by_bucket, render


def main(argv):
    if len(argv) != 1:
        print("usage: python3 -m rollup FILE", file=sys.stderr)
        return 2
    with open(argv[0]) as handle:
        events = [datetime.fromisoformat(line.strip()) for line in handle if line.strip()]
    print(render(count_by_bucket(events)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
