# registry-publish

Confirm the release job can authenticate to the internal registry:

    python3 tools/config_check.py

`config/publish.ini` holds references, not values: `${REGISTRY_TOKEN}` is
resolved from the environment at run time. The token is issued per release
engineer and is never written into the config.

`--print-config` resolves and prints the configuration with credential fields
masked. It performs no authentication and exits zero whether or not a token is
set, so it is not a substitute for the check above.
