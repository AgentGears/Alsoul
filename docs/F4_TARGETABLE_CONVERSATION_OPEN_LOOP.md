# F4 Targetable Conversation Open Loop

**Status:** Executable bounded Decision 13.B checkpoint  
**Publication:** GitHub-safe

This checkpoint makes one durable `ConversationOpenLoop` addressable without turning natural-language similarity, recency, or model inference into identity authority.

## Semantic boundary

```text
open_loop_id
≠ open_loop_reference_id
≠ canonical_reference_key
≠ current-input selector
```

`open_loop_id` remains canonical loop identity. `ConversationOpenLoopReference` is immutable source-grounded addressing metadata. A current counterpart input produces a bounded selector that may resolve an active loop, but the selector is not itself durable loop identity.

```text
ConversationOpenLoopReference
≠ MemoryClaim
≠ PersonClaim
≠ EvidenceItem
≠ DelegatedTask
≠ Commitment
≠ Trigger
≠ Permission / Approval
```

Addressability therefore grants no background-work, proactive-contact, or external-effect authority.

## F4 decision reference

Every newly admitted bounded `DECISION` loop is atomically created with one reference:

```text
COUNTERPART_INPUT
"I need to decide between A and B."
↓
ConversationOpenLoop OL1
+
ConversationOpenLoopReference LR1 {
    reference_kind = DECISION_OPTION_PAIR
    reference_contract_version = DECISION_OPTION_PAIR_V1
    canonical_reference_key = ["a","b"]
}
```

The v1 normalization contract is deliberately mechanical:

1. Unicode NFC normalization;
2. outer whitespace trimming;
3. internal whitespace collapse;
4. Unicode case folding;
5. lexical content otherwise preserved;
6. the two normalized options are sorted into an order-independent pair.

No stemming, synonym expansion, embedding search, ontology mapping, model interpretation, or latest-wins heuristic participates.

```text
"A" / "B" == "B" / "A"
"small option" != "smaller option"
"budget plan" != "cheap plan"
```

## Structured directive parsing

The bounded grammar separates operation from selector.

```text
"Back to that decision."
→ operation = RESUME
→ selector = UNQUALIFIED

"Back to the decision between A and B."
→ operation = RESUME
→ selector = DECISION_OPTION_PAIR_V1 / ["a","b"]
```

The same target-resolution layer may govern bounded `RESUME`, `RESOLVE`, and `CANCEL` operations.

## Resolution

Unqualified selection keeps Decision 13.A behavior:

```text
active DECISION loops = {}
→ UNAVAILABLE

active DECISION loops = {OL1}
→ OL1

active DECISION loops = {OL1, OL2}
→ AMBIGUOUS
```

Explicit selection uses exact durable reference equality:

```text
relationship = R1
AND loop is active
AND loop_kind = DECISION
AND reference_contract = pinned contract
AND reference_key = pinned key
```

Then:

```text
0 matches → TARGET_NOT_FOUND
1 match   → select it
>1 match  → AMBIGUOUS
```

There is no ranking phase.

Two different loops may intentionally have the same reference key. A reference collision never collapses loop identity.

## Projection lineage

A successful resume pins exact selection into immutable cognition state:

```text
ContextProjection
├── opening event
├── current input
├── selected open_loop_id
└── selector provenance
    ├── selection_basis
    ├── open_loop_reference_id? 
    ├── selector_contract_version?
    └── selector_key?
```

Schema v3 keeps the v2 `context_projection_open_loop_item` lineage row and adds `context_projection_open_loop_selector` for the stronger selector provenance. Existing v2 projections remain historical and readable without rewriting them.

Provider execution receives only the already-resolved loop. Candidate loops are never delegated to the model for referent choice.

Explicit-reference provider rendering uses `f4-renderer-v4`; existing unqualified and prior-Timeline contracts retain their earlier renderer identity because their provider-context shape is unchanged.

## Recovery and concurrency

Recovery reuses the committed selector provenance rather than re-resolving the original utterance.

Unqualified projections require the selected loop to remain the sole active `DECISION` loop.

Explicit projections require the selected loop to remain the sole active loop matching the exact pinned reference key and contract. An unrelated loop does not invalidate explicit selection; a second matching loop does.

```text
CP1 explicitly selected OL1 / ["a","b"]

add OL2 / ["c","d"]
→ CP1 may remain reusable

add OL3 / ["a","b"]
→ CP1 is no longer reusable
```

Closure of the selected loop likewise makes another provider execution from that projection ineligible. Historical projection membership is never rewritten.

## Migration compatibility

Schema v3 adds:

```text
conversation_open_loop_reference
context_projection_open_loop_selector
```

Migration from schema v2 backfills a decision reference only when it can be mechanically reconstructed from the canonical opening event under the frozen bounded opening grammar. It does not use a model or semantic approximation. A historical loop that cannot be proven reconstructable is left without invented reference metadata and remains usable only through otherwise-valid unqualified selection.

## F4 exclusions

This checkpoint does not implement:

- semantic Timeline search;
- embedding/vector reference lookup;
- model-selected referents;
- synonyms or paraphrase matching;
- latest-open-loop-wins behavior;
- arbitrary user-created labels;
- automatic supersession or expiry;
- work, scheduling, proactivity, or external action from open-loop state.

The purpose of Decision 13.B is precise conversational addressability without weakening identity, epistemic, recovery, or authority boundaries.
