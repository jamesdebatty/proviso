# manifest

Deployment manifests are layered: a base manifest is merged with a
per-environment override.

Verify a change with:

    python3 scripts/build.py

The build check parses every module and validates every schema file. CI runs
the same command.
