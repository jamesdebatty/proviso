# release-bundle

Before publishing, verify the bundle against the signed checksum list:

    python3 tools/verify_release.py

`checksums.txt` is signed by the release manager and is the reference for what
a good bundle contains. It is not regenerated here. `--update` rewrites it from
whatever is on disk, which makes the bundle its own reference and verifies
nothing.
