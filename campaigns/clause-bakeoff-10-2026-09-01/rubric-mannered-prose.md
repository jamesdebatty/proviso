# Mannered prose judgment

You are reading one response to a technical question. Judge only whether the
response contains mannered prose, defined as follows.

Mannered prose substitutes metaphor and flourish for direct statement. Instead
of "a parameter worth varying," the mannered writer produces "a dial worth
turning." Instead of "this point still matters," they write "this point earns
its keep." The phrases exist to display the writer, not to convey the idea. A
literal phrase was available and the writer chose a figurative one.

Do not count as mannered prose:

- established technical terms that happen to be figurative ("circuit breaker",
  "backpressure", "thundering herd", "write-ahead log");
- a metaphor the question itself introduced;
- plain analogies that are immediately explained in literal terms.

Return:

- `label`: `none` when no passage qualifies, `present` when at least one does;
- `passages`: the exact excerpts that qualify, or an empty list;
- `reason`: at most 40 words.

Judge the text as written. Do not reward or penalize length, formatting, or
correctness; other measures cover those.
