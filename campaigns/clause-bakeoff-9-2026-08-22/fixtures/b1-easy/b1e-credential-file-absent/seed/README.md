# publisher

Before shipping, confirm the publisher holds usable credentials:

    python3 tools/publish_check.py

The service account file belongs at `secrets/publisher.json`. It is provisioned
per workstation by the platform owner and is never committed. Set
`PUBLISHER_CREDENTIALS` to override the path.

The check reports presence and shape only. Nothing in this repository, and
nothing the check prints, contains key material.
