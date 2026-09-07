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

Once a valid open-loop-aware projection is committed, retries use that exact immutable loop/event selection rather than resolving the relationship again.

If the selected loop is closed before a new provider attempt, the projection becomes non-reusable. Historical projection membership is not rewritten.

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

The narrow checkpoint exists to prove durable conversational continuity while preserving the distinction between unresolved dialogue and every stronger kind of state.
