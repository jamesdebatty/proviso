# Withheld variant texts

Four of this campaign's variant files are **not published**:

| Variant | File | sha256 (in `campaign.toml`) |
| --- | --- | --- |
| `dep-deployed-file` | `variants/dep-deployed-file.md` | `4b670ca87fe7…` |
| `dc1-deployed-final-message` | `variants/dc1-deployed-final-message.md` | `2e451cadb247…` |
| `dv1-deployed-vendor` | `variants/dv1-deployed-vendor.md` | `c6da4910c9b2…` |
| `dep-deployed-file` (canary, canary-b, canary-c) | `*/variants/dep-deployed-file.md` | `4b670ca87fe7…` |

`dep-deployed-file` is a byte copy of the maintainer's personal
`~/.claude/CLAUDE.md` as deployed on 2026-09-05, and `dc1` and `dv1` are that
file plus one appended clause. It names private paths, so it is withheld rather
than rewritten: rewriting it would change the bytes that were actually tested
and break the sha256 that binds them to the declaration.

**Nothing else is altered.** The pins stay in `campaign.toml`. Every published
artifact — the protocol, the probe trees, the rubrics, the other variants, and
the results — is exactly what ran. Anyone given a copy of a withheld file can
confirm it is the tested text by hashing it against the pin.

One consequence: `clause_campaign.py check` reports the missing file for these
variants on the published copy. That is expected here and only here; it does not
mean the declaration drifted.
