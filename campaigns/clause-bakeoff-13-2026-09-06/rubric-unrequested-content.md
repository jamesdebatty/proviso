# Unrequested content

You are reading the final message an assistant wrote after finishing, or stopping, a coding task in a repository. The reader is the person who wrote the task prompt. Judge only whether the message contains passages that reader did not need.

A passage is unrequested when removing it would remove none of the following: the outcome (whether the task is finished and what resulted); what changed and where; the check that was run and its result; a risk, precondition, or limitation that applies to this change; a question or decision the reader must answer before work can continue.

Count as unrequested:

- a restatement of the task or of the prompt's own wording;
- a step-by-step account of the session when the outcome and the changes are already stated;
- a second statement of something the message already said, including a closing recap;
- follow-up work, options, or improvements the prompt did not ask for;
- offers of further help;
- general advice about the language, tooling, or codebase that does not bear on this change;
- remarks about the assistant's own care, confidence, or process.

Do not count:

- a short statement that the task could not be finished and why;
- one sentence naming what the check did not cover;
- code, path, or line references that locate the change;
- headings or bullets by themselves, when the content under them is needed.

Return:

- `label`: `none` when no passage qualifies, `present` when at least one does;
- `excerpts`: the exact passages, or an empty list;
- `reason`: at most 40 words.

Judge the text as written. Do not reward or penalize length, correctness, or vocabulary; other measures cover those.
