import sys

from tally.words import count_words


def main(argv):
    if len(argv) != 1:
        print("usage: python3 -m tally FILE", file=sys.stderr)
        return 2
    with open(argv[0]) as handle:
        counts = count_words(handle.read())
    for word in sorted(counts):
        print(f"{word}\t{counts[word]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
