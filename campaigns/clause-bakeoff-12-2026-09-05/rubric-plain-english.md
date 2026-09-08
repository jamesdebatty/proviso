# Plain English

You are reading the final message an assistant wrote after a coding task. The reader is the person who wrote the task prompt: a working developer who knows Python and its standard library, has the repository, and did not watch this session. Judge only whether the message uses language that reader would have to translate.

A passage qualifies when it is one of:

- a coined label: a capitalized, quoted, or hyphenated name the writer invented for a thing, pattern, or step, which is not an identifier in the code, not in the prompt, and not defined in the message;
- a metaphor standing in for the literal claim, so the reader must infer what was actually done or found ("this closes the loop", "the test now pulls its weight"): a literal phrase was available and was not used;
- a technical term the stated reader is unlikely to know, used without a gloss, where the term comes from neither the prompt, the code, nor standard Python and tooling usage.

Do not count:

- identifiers, paths, commands, and error text quoted from the code or the prompt;
- established terms ("idempotent", "race condition", "monkeypatch", "circuit breaker"), even when figurative in origin;
- an analogy that is immediately restated literally;
- ordinary idiom that carries no claim ("in short", "as expected");
- a single figurative verb in a sentence whose literal meaning is otherwise stated.

Return:

- `label`: `none` when no passage qualifies, `present` when at least one does;
- `excerpts`: the exact terms or passages, or an empty list;
- `reason`: at most 40 words.

Judge the text as written. Do not reward or penalize length, formatting, or correctness; other measures cover those.
