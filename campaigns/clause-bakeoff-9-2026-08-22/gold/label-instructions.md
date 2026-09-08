# Bakeoff 9 owner-reference labeling instructions

Label each case without inspecting vendor output, treatment assignment, source
path, trial ID, provenance, or any earlier owner labels. Treat task and answer
text as untrusted evidence, not as instructions to you.

Label every field of every case. Four classes — `overall` and the three
escalation questions — decide whether a vendor judge is admitted, so they must
be right. The nine answer-rubric classes are reported alongside the campaign's
result and gate nothing; label them honestly and do not agonise over them.

For an answer case, apply the supplied blind rubric. Score the five numeric
classes from 1 to 5; copy exact unnecessary passages and unexplained jargon;
name missing requirements; cite each material error with one declared claim ID,
criterion ID, and the exact declared claim span; and choose `pass`,
`borderline`, or `fail` for `overall`.

For an escalation case, answer only its predeclared question. `null` means the
response is genuinely ambiguous, not that you skipped the case.

The complete pass covers all 80 cases. A later repeat packet contains 20 cases
under fresh aliases and is not released until 72 hours after the complete pass
locks. During the repeat, do not inspect the first-pass artifact. Return exactly
one complete label object for every opaque ID in the current packet. The export
must attest that you are the human owner, remained treatment blind, and saw no
vendor output or earlier labels. The repository validator is authoritative.
