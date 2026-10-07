You are cross-checking a long meeting that was documented in parts. Each part was documented on its own, so an item from an early part may have been resolved, replaced or repeated in a later part.

## Input
1. The summary of each part, in order.
2. Every item from every part, one per line, as `[ID] (part N) TYPE: text`:
   - IDs starting with D are decisions, A are action items, O are open items (proposals or questions).
   - Owners and deadlines are shown in brackets where stated.

## Your two jobs

### 1. Removals
List the items that should NOT appear in the final record, each with the later item that replaces it. Only these four reasons are allowed:
- **accepted_later**: an open proposal (O) that a later decision (D) or action item (A) shows was accepted. Example: "O1 (part 1) Proposal: move reporting jobs to Airflow" is replaced by "D5 (part 4) Decided to move reporting jobs to Airflow".
- **answered_later**: an open question (O) that a later decision (D) or action item (A) clearly answers.
- **superseded**: a decision (D) that a later decision changed or reversed, or an action item (A) that a later action item replaced. Keep only the final outcome.
- **duplicate**: the same item recorded twice (same type, same meaning). Remove the less complete one; `replaced_by` is the one to keep.

Be conservative. Only remove an item when a specific other item clearly resolves, replaces or repeats it. Two items about the same topic are not duplicates if they say different things. When unsure, remove nothing. Never remove an item just because it seems unimportant.

### 2. Summary
Write a 3–6 sentence summary of the whole meeting from the part summaries and the items, reflecting final outcomes (not decisions that were later reversed). Use only information given in the input.

## Output
`removals`: a list of {"item": "O1", "replaced_by": "D5", "reason": "accepted_later"}. Use an empty list if nothing should be removed.
`summary`: the overall summary.
