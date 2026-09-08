"""Parse and format windows written as text like ``9-12,11-13``."""

from windows.merge import merge


def parse(text):
    """Turn ``"9-12,11-13"`` into ``[(9, 12), (11, 13)]``."""
    out = []
    for item in text.split(","):
        if not item.strip():
            continue
        start, end = item.split("-")
        out.append((int(start), int(end)))
    return out


def format_windows(intervals):
    return ",".join(f"{start}-{end}" for start, end in intervals)


def main(argv):
    if len(argv) != 1:
        return 2
    windows = parse(argv[0])
    print(format_windows(windows))
    return 0
