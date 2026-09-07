# F4 Conversation Open Loop

**Status:** Executable bounded Decision 13.A checkpoint  
**Publication:** GitHub-safe

This checkpoint implements the first durable `ConversationOpenLoop` in the F4 runtime without turning conversation history into memory, delegated work, or background authority.

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

## Bounded F4 grammar

The first executable kind is `DECISION`.

A bounded opening form such as:

```text
I need to decide between A and B.
```

may admit a durable open loop whose canonical source is that exact `COUNTERPART_INPUT` Timeline event.

A bounded resume form such as:

```text
Back to that decision.
```

requires exactly one unresolved `DECISION` loop in the relationship. If none exists, execution fails closed. If more than one exists, execution fails closed rather than selecting the newest loop.

The current terminal forms admit explicit `RESOLVED` or `CANCELLED` closure. The physical lifecycle also reserves `SUPERSEDED` and `EXPIRED` as already-defined terminal kinds, but F4 does not autonomously create those transitions.

## Physical lifecycle

Opening and closure are separate append-oriented records:

```text
COUNTERPART_INPUT
↓
ConversationOpenLoop
↓
optional later terminal closure
    RESOLVED
    CANCELLED
    SUPERSEDED
    EXPIRED
```

The open-loop row has no mutable status. Currentness is derived from the absence of a terminal closure row.

The current schema adds:

```text
conversation_open_loop
conversation_open_loop_closure
context_projection_open_loop_item
```

`context_projection_open_loop_item` gives cognition explicit lineage to the exact durable loop selected for one immutable `ContextProjection`.

Schema v2 is composed without mutating the metadata frozen into schema v1. Migration revision `0001_f4_foundation` therefore remains reproducible, while revision `0002_conversation_open_loop` advances an existing or newly initialized store to the current schema.

## Relationship-scoped continuity

Unlike immediate-prior Timeline context, a `ConversationOpenLoop` is relationship-scoped rather than thread- or route-scoped.

```text
same RelationshipState
+
exactly one unresolved matching loop
→ bounded resume may select it
```

A later interaction can therefore resume the loop after intervening dialogue or a new conversation/thread without pretending that the old event was admitted memory.

This does not make arbitrary cross-thread history retrievable. Only an explicitly admitted open loop is eligible for this path.

## Cognition projection

For the bounded resume path:

```text
ConversationOpenLoop OL1
    opened_by_event = I1

... intervening Timeline events ...

current input I7
    "Back to that decision."

↓

ContextProjection CP1
    selected_event_refs = [I1, I7]
    selected_open_loop = OL1
    selection_basis = CURRENT_OPEN_DECISION_LOOP
    personal_context_items = []
    world_context_items = []
```

Provider rendering places the selected loop in a dedicated `conversation_open_loop_context` field. It is not rendered as a PersonClaim, MemoryClaim, or WorldResult.

The model does not choose which loop is selected. Selection occurs before provider execution under the deterministic host contract.

The provider-context contract changes at this checkpoint, so the renderer identity advances to:

```text
f4-renderer-v3
```

Renderer identity is part of invocation provenance; a new rendered field is not treated as the same wire contract under an old renderer version.

## Recovery compatibility

A durable projection created before this open-loop selection contract may contain only the current resume input. Such a projection remains historical state but is not reusable cognition context.

```text
resume input
+
legacy ContextProjection without open-loop lineage
↓
INPUT_ADMITTED for current execution
↓
build new ContextProjection with exact loop lineage
↓
new provider attempt if needed
```

An already-generated candidate attached to the incompatible legacy projection is not adopted merely because it is durable.

Once a valid open-loop-aware projection is committed, recovery preserves its exact immutable loop/event lineage. Reuse is still conditional: immediately before another provider execution, Alsoul re-evaluates the complete active `DECISION` loop set for the relationship.

```text
selected OL1 remains open
+
active matching loops = {OL1}
→ projection may remain reusable

selected OL1 closed
→ projection non-reusable

active matching loops = {OL1, OL2, ...}
→ projection non-reusable
→ fresh selection is ambiguous
```

This extra fence matters because another already-admitted Timeline event can later be admitted as a second open loop without advancing the Timeline frontier. Timeline equality alone therefore cannot prove that the earlier open-loop selection remains unambiguous.

Historical projection membership is never rewritten when reuse becomes invalid.

## Authority exclusions

The presence of an unresolved loop has no implication for:

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
- model-selected history retrieval;
- latest-open-loop-wins behavior;
- automatic expiry;
- automatic supersession;
- background work from conversational state;
- proactive reminders or contact;
- conversion of open-loop content into MemoryClaim.

## Acceptance contract

The executable suite must prove at least:

1. bounded decision-opening text can create one durable relationship-scoped `ConversationOpenLoop` without creating memory or world work;
2. replay of the same opening source is idempotent;
3. bounded resume can cross intervening dialogue and conversation/thread changes while remaining in the same RelationshipState;
4. resume projects exactly the opening event and current input and records explicit `ContextProjection → ConversationOpenLoop` lineage;
5. provider context carries the selected loop separately from personal/world proposition context;
6. the open-loop provider rendering contract records `renderer_version = f4-renderer-v3`;
7. explicit `RESOLVED` and `CANCELLED` transitions are append-oriented terminal closures;
8. a closed loop cannot be resumed;
9. multiple unresolved matching loops fail closed rather than selecting the latest;
10. projection reuse rechecks the complete active matching-loop set and rejects a projection if another loop becomes active without Timeline advancement;
11. a legacy projection without open-loop lineage is not reusable for a resume input, even if it already has a generated candidate;
12. schema v1 metadata remains frozen while schema v2 composes the current runtime schema; and
13. migration upgrade to current head and downgrade to base both succeed.

The narrow checkpoint exists to prove durable conversational continuity while preserving the distinction between unresolved dialogue and every stronger kind of state.
