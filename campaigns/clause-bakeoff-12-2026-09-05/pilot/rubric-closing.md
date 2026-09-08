# How the message ends

You are reading the final message an assistant wrote after a coding task,
together with the task prompt. First find the closing unit: the message's
final paragraph, or its final list when it ends in one (items separated by
blank lines are still one list), ignoring any code block or table after it.
Classify what the closing unit does, using the rest of the message and the
prompt as context. Choose exactly one label.

- `result`: it states what was done, what was found, what a check showed or
  could not show, or the direct answer to the question asked.
- `handoff`: it invites the reader to request further work, or asks the reader
  to pick between options, while the message as a whole presents the task as
  done. Forms include an offer to make a change, a request to be told which
  variant is wanted, and a conditional such as "if you want X, I can".
- `aside`: it raises behaviour, risk, or work outside what the task asked, with
  no invitation and no question, including a remark that something was left as
  it was.
- `blocked`: it asks for information without which the task cannot be finished,
  or reports a stop for that reason, and the message as a whole presents the
  task as unfinished.
- `none`: the message has no closing unit, because it is only code or a table.

Precedence when a unit does more than one: a `handoff` that concerns optional
work counts as `handoff` even inside a message that is otherwise `blocked`; a
question that is needed to finish is `blocked`, not `handoff`; otherwise
`handoff` over `aside` over `result`.

Return:

- `label`: one of the five above;
- `excerpts`: the sentences that decided it, quoted exactly, or an empty list
  for `none`;
- `reason`: at most 40 words.

Judge the text as written; do not reward or penalize length, correctness, or
vocabulary.
