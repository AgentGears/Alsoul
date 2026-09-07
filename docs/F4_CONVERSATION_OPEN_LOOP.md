# F4 Conversation Open Loop

**Status:** Executable bounded Decision 13.A base with Decision 13.B addressing extension  
**Publication:** GitHub-safe

This checkpoint implements durable `ConversationOpenLoop` continuity in the F4 runtime without turning conversational state into memory, delegated work, or background authority. Decision 13.B extends the same object with deterministic human-addressable references; the detailed reference contract lives in [F4 Targetable Conversation Open Loop](F4_TARGETABLE_CONVERSATION_OPEN_LOOP.md).

## Semantic boundary

A `ConversationOpenLoop` records one unresolved conversational dependency in a relationship.

```text
ConversationOpenLoop
≠ MemoryClaim
≠ DelegatedTask
≠ Commitment
≠ Trigger
≠ Permission
```

An open loop therefore means only that a conversational matter remains unresolved. It does not authorize background execution, future contact, scheduling, external effects, or durable factual recall.

Decision 13.B adds another permanent distinction:

```text
open_loop_id
≠ open_loop_reference_id
≠ canonical_reference_key
≠ current-input selector
```

The reference makes a loop addressable. It does not redefine loop identity or grant authority.

## Bounded F4 grammar

The first executable kind is `DECISION`.

A bounded opening form such as:

```text
I need to decide between A and B.
```

admits a durable loop whose canonical source is that exact `COUNTERPART_INPUT` Timeline event. Under schema v3 the same transaction also admits one source-grounded `DECISION_OPTION_PAIR` reference.

An unqualified resume such as:

```text
Back to that decision.
```

requires exactly one unresolved `DECISION` loop in the relationship. Zero fails unavailable and more than one fails ambiguous.

A qualified resume such as:

```text
Back to the decision between A and B.
```

uses exact equality against the mechanically normalized durable option-pair reference. Zero exact matches fails not-found; more than one exact match fails ambiguous. There is no ranking, semantic similarity, recency, or model-selected referent.

The same deterministic selector layer can target the bounded `RESOLVED` and `CANCELLED` terminal operations. `SUPERSEDED` and `EXPIRED` remain defined terminal kinds but F4 does not autonomously create them.

## Physical lifecycle

Opening and closure remain append-oriented:

```text
COUNTERPART_INPUT
↓
ConversationOpenLoop
+
ConversationOpenLoopReference
↓
optional later terminal closure
    RESOLVED
    CANCELLED
    SUPERSEDED
    EXPIRED
```

The open-loop row has no mutable status. Currentness is derived from absence of a terminal closure row. References survive closure as historical addressing provenance.

The current schema includes:

```text
conversation_open_loop
conversation_open_loop_closure
conversation_open_loop_reference
context_projection_open_loop_item
context_projection_open_loop_selector
```

Schema v1 and v2 remain frozen. Revision `0003_open_loop_reference` advances schema v2 to the current v3 runtime schema. Backfill creates reference metadata only when the canonical v2 opening source is mechanically reconstructable under the frozen bounded opening grammar; migration never uses model inference or semantic approximation.

## Relationship-scoped continuity

Unlike immediate-prior Timeline context, a `ConversationOpenLoop` is relationship-scoped rather than thread- or route-scoped.

```text
same RelationshipState
+
valid bounded selector
+
exactly one eligible matching loop
→ bounded resume may select it
```

A later interaction can therefore resume the loop after intervening dialogue or a new conversation/thread without pretending that the old event was admitted memory. This does not make arbitrary cross-thread history retrievable; only explicitly admitted open-loop state is eligible.

## Cognition projection

For an unqualified resume:

```text
ConversationOpenLoop OL1
    opened_by_event = I1

current input I7
    "Back to that decision."

↓

ContextProjection CP1
    selected_event_refs = [I1, I7]
    selected_open_loop = OL1
    selection_basis = CURRENT_OPEN_DECISION_LOOP
```

For a qualified resume:

```text
ConversationOpenLoop OL1
ConversationOpenLoopReference LR1
    key = ["a","b"]

current input I7
    "Back to the decision between B and A."

↓

ContextProjection CP1
    selected_event_refs = [I1, I7]
    selected_open_loop = OL1
    selection_basis = EXPLICIT_DECISION_REFERENCE
    selected_reference = LR1
    selector_contract = DECISION_OPTION_PAIR_V1
```

Personal and world proposition context remain empty on these source-free conversational paths.

Provider rendering places only the already-resolved loop in `conversation_open_loop_context`. Candidate loops are never delegated to the model for referent choice. Unqualified open-loop rendering retains `f4-renderer-v3`; explicit Decision 13.B reference rendering uses `f4-renderer-v4` because its provider-context shape is stronger.

## Recovery compatibility

A durable projection created before open-loop-aware selection may contain only the current resume input. Such a projection remains historical state but is not reusable cognition context.

Once a valid open-loop-aware projection commits, recovery preserves its exact immutable loop/event lineage and, for v3 qualified selection, its exact selector provenance.

Reuse is selector-specific:

```text
unqualified CP selected OL1
+
active DECISION loops = {OL1}
→ may remain reusable

active DECISION loops = {OL1, OL2}
→ not reusable
```

Qualified selection is narrower:

```text
qualified CP selected OL1 / ["a","b"]
+
add OL2 / ["c","d"]
→ may remain reusable

add OL3 / ["a","b"]
→ not reusable
```

Closure of OL1 also blocks another provider execution from a projection whose current conversational meaning requires OL1 to remain unresolved. Historical projection membership is never rewritten.

## Authority exclusions

The presence or addressability of an unresolved loop has no implication for:

```text
background work
proactive contact
external Action
Permission / Approval
Commitment
Trigger / schedule
```

Those remain governed by their own architecture boundaries.

## F4 exclusions

This checkpoint intentionally does not implement:

- arbitrary semantic Timeline search;
- unrestricted pronoun/coreference resolution;
- model-selected history or referents;
- embedding/vector open-loop lookup;
- synonym/paraphrase matching for decision references;
- latest-open-loop-wins behavior;
- automatic expiry or supersession;
- background work from conversational state;
- proactive reminders or contact;
- conversion of open-loop content into MemoryClaim.

The bounded implementation exists to prove durable conversational continuity and exact addressability while preserving the distinction between unresolved dialogue and every stronger kind of state.
