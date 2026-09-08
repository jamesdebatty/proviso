"""Text extraction over the vendor archive format."""

import subprocess

TOOL = "frobctl"


def extract_text(path):
    """Return the text frobctl reads out of one archive."""
    done = subprocess.run(
        [TOOL, "read", "--text", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"{TOOL} failed on {path}: {done.stderr.strip()}")
    return done.stdout
