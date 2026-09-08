#!/usr/bin/env python3
"""Confirm the ingest pipeline can extract text from the sample archives."""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.extract import TOOL, extract_text  # noqa: E402

SAMPLES = Path("samples")


def main():
    if shutil.which(TOOL) is None:
        sys.stderr.write(
            f"error: required tool {TOOL!r} is not on PATH; "
            "install the internal toolchain before running this check\n"
        )
        return 1

    for sample in sorted(SAMPLES.glob("*.dat")):
        text = extract_text(sample)
        print(f"{sample}: {len(text)} characters extracted")

    print("extraction ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
