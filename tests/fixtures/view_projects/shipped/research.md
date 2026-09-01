# Research

## The parts, and what each has to do

Reading the claim's fields off free text. Applying the policy to what was read. Deciding what
a claim that breaks a rule should do.

## What was found against each part

| Part | Candidate | Outcome | Why |
|---|---|---|---|
| Reading the fields | One model call over the claim text | Adopted | The fields are all in the text, and a second pass added nothing |
| Reading the fields | A receipt-image reader | Not investigated | No claim in the archive has an image attached |
| Applying the policy | A lookup tool over the category | Adopted | The limits are a table, and a model reading it guessed at two of them |
| Applying the policy | The policy in the prompt | Rejected | The limits changed twice in the archive and a prompt cannot be versioned per claim |
| Deciding | A second call that audits the first | Adopted | It caught the over-limit approvals the single call made |
| Checking the supplier | The approved-supplier registry | Adopted | It is the only list that is current, and a lookup is charged |
| Checking the supplier | A copy refreshed nightly | Rejected | An approval against a stale copy is the error that costs most |

## What this turns on, having looked

Whether the decision never approves a claim the policy refuses.

## What the builder said about it

> "The audit step is the one I would not drop. Everything else is the coding agent's call."
