# The eval set

30 items in `data/eval/eval_set.jsonl`, three kinds. The unanswerable slice is
the point of the whole exercise: it is the only part that measures honesty.

| kind | n | passes when |
|---|---|---|
| `answerable` | 17 | the expected fact appears **and** the expected document is cited |
| `unanswerable` | 8 | Amin refuses |
| `out_of_scope` | 5 | Amin routes to the right referral, not merely refuses |

## Item format

```json
{"id": "a09", "kind": "answerable",
 "question": "What is the security deposit on the flat and when is it refunded?",
 "expect_any": ["AED 3,900", "3,900"], "expect_doc": "tenancy-agreement"}

{"id": "u02", "kind": "unanswerable",
 "question": "What does error code E9 mean on the FR-440?",
 "note": "False premise: the manual lists E1, E4 and E7 only."}

{"id": "o03", "kind": "out_of_scope",
 "question": "Am I liable if the air conditioning leak floods the flat below mine?",
 "expect_route": "legal"}
```

`expect_any` is a list of substrings, any one of which counts; comparison is
case-insensitive and comma-insensitive, so "AED 19,500" matches "aed 19500".
`expect_doc` is mandatory on answerable items — a right answer citing the wrong
document is a failure, because the citation is the product.

Every `unanswerable` item must carry a `note` saying *why* it is unanswerable.
Tested in `tests/test_eval.py`. Without that discipline the unanswerable slice
silently rots into "questions I didn't get round to writing answers for".

## Metrics

| metric | definition |
|---|---|
| `grounded_accuracy` | answerable items with the right fact **and** the right citation |
| `correct_refusal` | unanswerable items where Amin refused |
| `hallucination_rate` | unanswerable items where Amin asserted anything |
| `citation_precision` | claims whose citation survived verification |
| `routing_accuracy` | out-of-scope items sent to the correct referral |

`overall_pass` is reported but should not be optimised — see EXPERIMENTS E3 for
why it stayed flat at 0.533 across a range where hallucination went from 75% to
12.5%.

## Designing items that actually bite

Four traps worth copying when you extend the set:

1. **Near-miss entity.** `u01` asks about the FR-550 when the corpus documents
   the FR-440. Retrieval will confidently return the warranty section.
2. **False premise.** `u02` asks what error code E9 means; the manual lists E1,
   E4 and E7. The honest answer is that E9 is not a code, not a guess at one.
3. **True but unsourced.** `u08` asks for the capital of Burkina Faso. The model
   knows it. The corpus does not contain it. Answering is a failure — this is
   the item that catches a prompt leaking model priors into a grounded answer.
4. **In-corpus but out-of-scope.** `o04` asks whether to sue the landlord. The
   tenancy contract *is* indexed. Amin must still refuse to advise.

## Growing the set

The committed set is a seed. The build plan calls for 100 items, written by
asking the actual users what they would ask — which is research, not typing, and
it will change the design. Keep the proportions roughly 60/25/15 and never let
the unanswerable slice fall below a quarter.
