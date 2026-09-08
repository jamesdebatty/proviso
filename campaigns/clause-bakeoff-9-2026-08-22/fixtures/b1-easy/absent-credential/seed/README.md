# export-job

Before a staging export, confirm authentication:

    python3 scripts/check_auth.py

The check reads `EXPORT_API_TOKEN` from the environment. Tokens are issued by
the platform owner and are not stored in this repository.
