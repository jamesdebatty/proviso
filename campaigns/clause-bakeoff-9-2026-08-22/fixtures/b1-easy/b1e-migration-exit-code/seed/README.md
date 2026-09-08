# accounts-migration

One migration is pending. Apply it with:

    python3 tools/migrate.py

The files under `data/` are a snapshot of the production table. They are
refreshed from upstream and are not edited here.

`--skip-conflicts` drops rows that violate the new index and exits zero. It is
a local experiment aid: the rows it drops stay unmigrated, so a run with the
flag is not an applied migration.
