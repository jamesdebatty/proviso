# proviso

Bakeoff campaigns measuring how a conditional clause in an agent's instructions
changes what the agent actually does. A proviso is a conditional clause, which
is what these campaigns test: you add one to a configuration file, run the arms
against pinned probes, and let blind graders decide whether the behaviour moved.

**Status: active.** Published as an export from a private lab, so the history
here is a series of exports rather than the development history.

## What you can run offline

The unit suite is Python standard library only, Python 3.11 or newer:

```sh
python3 -m unittest discover -s tests
```

Some tests skip by design, each saying why: two drive a pinned CLI binary no
clone carries (set `BAKEOFF9_CLAUDE_BINARY` to that binary to run them), and the
rest read raw campaign artifacts that are retained privately. The
`clause-shipper-smoke` synthetic campaign also runs offline with no keys.

## What a live bakeoff needs

Pinned local CLI binaries, named by sha256 in each campaign's `campaign.toml`,
and real subscription quota. Live generation is capability-gated: a campaign
dispatches nothing without an authorization file naming the plan hash. That is
deliberate — these runs cost money and cannot be silently re-run.

## What each campaign ships

Its preregistration, protocol, rubrics, variants, probes, and analysis plan —
enough to audit the design and re-derive the result. `campaign.toml` binds all
of it by hash, and `clause_campaign.py check` verifies the binding.

**Raw campaign artifacts are retained privately and available on request.** Run
outputs, trial transcripts, and per-trial records are not published; the reports
are synthesized from them.

Four variant texts are withheld because they are a byte copy of the maintainer's
personal configuration. Their hashes remain in `campaign.toml`, so anyone given
a copy can confirm it is the tested text — see
`campaigns/clause-bakeoff-11-2026-09-05/variants/WITHHELD.md`.

## Contributions

Issues are welcome. Pull requests are declined: each release replaces the tree
wholesale, so a merged pull request would be erased by the next export.

## License

MIT. See `LICENSE`. The excerpt in `sources/` is redistributed under its own MIT
licence, with the required notice in the file.
