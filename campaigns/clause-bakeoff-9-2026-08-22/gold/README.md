# Bakeoff 9 solo-owner reference handoff

The workflow is treatment-blind and local. It never uses model labels as owner
labels and never calls a vendor.

1. Derive an opaque owner ID:

   ```sh
   python3 scripts/bakeoff9_gold.py human-id 'private owner pseudonym'
   ```

2. Create and complete the 80-case owner-pass draft outside the repository,
   then finalize it. Finalization records the current UTC lock time.
3. Request the repeat packet. The command refuses until exactly 72 hours after
   the owner pass locked. The released packet contains 20 deterministic cases
   under fresh aliases and no first-pass labels.
4. Complete and finalize the repeat without opening pass one.
5. Generate and complete the self-adjudication draft. Originals remain embedded
   unchanged; disagreements require rationales.
6. Assemble `owner-reference.json`. The loader recomputes membership, repeat
   selection, timing, labels, intra-rater metrics, self-adjudication, source
   hashes, rubric, instructions, schemas, and the final artifact hash.

Run `python3 scripts/bakeoff9_gold.py --help` for the exact commands. Drafts are
mutable working files; every finalized artifact is immutable and refuses a
different existing target.
