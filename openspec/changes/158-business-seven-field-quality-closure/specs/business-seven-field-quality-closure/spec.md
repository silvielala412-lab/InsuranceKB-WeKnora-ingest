# Business Seven-field Quality Closure Specification

## M158-R1 Long-field shards

The compiler MUST split long legal fields into bounded section/page shards after recording an
all-readable-page scan receipt. It MUST merge atomic results deterministically without dropping
distinct conditions or accepting truncated provider output.

## M158-R2 Evidence admission

The compiler MUST admit a field from the verified Evidence subset only when every retained atomic
claim remains supported. Redundant unresolved Evidence MUST NOT veto an otherwise fully supported
field, and unresolved unique support MUST continue to fail closed.

## M158-R3 Coupled short fields

Payment term and frequency MUST be evaluated together. Waiting-period and policy-right values MUST
retain exceptions, consequences and current-product applicability found in the supplied material.
Examples and other-contract clauses MUST NOT be promoted to current-product facts.

## M158-R4 Feedback assessment

The evaluator MUST compare the final output with all 30 seven-field feedback records without
injecting expected answers into extraction. Non-machine-readable screenshot answers MUST remain
explicitly not scorable.

## M158-R5 Bounded validation

The run MUST preserve M157, remain within 32 qwen-plus calls, maintain at least 133/143 material-
supported present fields, produce independent immutable artifacts and update local preview only
after contract validation succeeds. The frontend parser MUST admit up to 32 total call receipts,
including more than four receipts for one product when the total remains bounded, and MUST reject
the thirty-third call.
