# ingest

Confirm the extractor works end to end:

    python3 tools/extract_check.py

Extraction shells out to `frobctl`, the archive reader from the internal
toolchain. It is installed by the workstation setup script and is not vendored
here.
