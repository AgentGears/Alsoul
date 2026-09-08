# F4 Conversation Open Loop

**Status:** Executable bounded Decision 13.A base with Decisions 13.B–13.C addressing extensions  
**Publication:** GitHub-safe

This checkpoint implements durable `ConversationOpenLoop` continuity in the F4 runtime without turning conversational state into memory, delegated work, or background authority. Decision 13.B adds deterministic source-derived references; Decision 13.C adds explicit counterpart-authored aliases. Detailed contracts live in [F4 Targetable Conversation Open Loop](F4_TARGETABLE_CONVERSATION_OPEN_LOOP.md) and [F4 Conversation Open Loop Alias](F4_CONVERSATION_OPEN_LOOP_ALIAS.md).

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

An open loop means only that a conversational matter remains unresolved. It does not authorize background execution, future contact, scheduling, external effects, or durable factual recall.

Addressing state remains separate:

```text
open_loop_id
≠ open_loop_reference_id
≠ open_loop_alias_id
≠ canonical reference/alias key
≠ current-input selector
```

A reference or alias makes a loop addressable. Neither redefines loop identity or grants authority.

## Bounded F4 grammar

The first executable kind is `DECISION`.

A bounded opening such as:

```text
I need to decide between A and B.
```

admits a durable loop whose canonical source is that exact `COUNTERPART_INPUT` Timeline event. The same transaction admits one source-grounded `DECISION_OPTION_PAIR_V1` reference.

An unqualified resume:

```text
Back to that decision.
```

requires exactly one unresolved `DECISION` loop in the relationship. Zero fails unavailable and more than one fails ambiguous.

A source-reference resume:

```text
Back to the decision between A and B.
```

uses exact equality against the mechanically normalized durable option-pair reference. Zero exact matches fails not-found; more than one exact match fails ambiguous. There is no ranking, semantic similarity, recency, or model-selected referent.

Decision 13.C permits an explicit user label after an exact target is already available:

```text
Call the decision between A and B "work laptop".
```

Later:

```text
Back to decision "work laptop".
```

uses exact `USER_LABEL_V1` alias equality. Alias assignment itself fails closed if the referenced target is missing or ambiguous. Alias selectors also support bounded resolve/cancel, while alias remove/rename have their own append-oriented alias lifecycle.

## Physical lifecycle

Opening and closure remain append-oriented:

```text
COUNTERPART_INPUT
↓
ConversationOpenLoop
+
ConversationOpenLoopReference
+
optional ConversationOpenLoopAlias
↓
optional alias retirement
    REMOVED
    RENAMED
↓
optional loop closure
    RESOLVED
    CANCELLED
    SUPERSEDED
    EXPIRED
```

The open-loop row has no mutable status. Currentness is derived from absence of a terminal closure. References and aliases survive closure as historical provenance. Alias retirement does not close the loop, and loop closure does not erase alias history.

The current schema includes:

```text
conversation_open_loop
conversation_open_loop_closure
conversation_open_loop_reference
conversation_open_loop_alias
conversation_open_loop_alias_retirement
context_projection_open_loop_item
context_projection_open_loop_selector
context_projection_open_loop_alias_selector
```

Schema v1–v3 remain frozen. Revision `0004_open_loop_user_alias` advances v3 to the current v4 runtime schema. Decision 13.B reference migration backfills only mechanically reconstructable source-derived references. Decision 13.C performs no alias backfill because earlier state contains no canonical counterpart-authored alias-assignment contract.

## Relationship-scoped continuity

`ConversationOpenLoop` addressing is relationship-scoped rather than thread- or route-scoped.

```text
same RelationshipState
+
valid bounded selector
+
exactly one eligible matching loop
→ bounded resume may select it
```

A later interaction can therefore resume admitted loop state after intervening dialogue or a new conversation/thread without pretending that old Timeline content became MemoryClaim. This does not make arbitrary history retrievable.

## Cognition projection

Unqualified, source-reference, and alias selections are resolved before provider execution and pinned into immutable `ContextProjection` provenance.

```text
unqualified
→ selection_basis = CURRENT_OPEN_DECISION_LOOP

explicit option pair
→ selection_basis = EXPLICIT_DECISION_REFERENCE
→ selected reference + DECISION_OPTION_PAIR_V1 key

explicit user alias
→ selection_basis = EXPLICIT_USER_ALIAS
→ selected alias + USER_LABEL_V1 key
```

Personal and world proposition context remain empty on these source-free conversational paths. The model receives only the already-resolved loop; candidate loops or alias candidates are never delegated to the model.

Renderer provenance remains contract-specific:

```text
unqualified open loop          → f4-renderer-v3
explicit Decision 13.B ref     → f4-renderer-v4
explicit Decision 13.C alias   → f4-renderer-v5
```

## Recovery compatibility

A durable projection created before the required addressing lineage existed remains historical state but is not automatically reusable cognition context.

Once a valid selection commits, recovery preserves that exact selection and revalidates only the semantics necessary for another provider execution.

```text
unqualified selection
→ selected loop must remain the sole active DECISION loop

explicit source reference
→ selected loop must remain the sole active loop matching the pinned reference

explicit user alias
→ selected loop must remain active
→ pinned alias must remain unretired
→ pinned alias must remain the sole active exact alias match
```

Unrelated loops therefore do not invalidate explicit source-reference or alias selections. Closure of the selected loop, a second matching source reference, or retirement/integrity loss of a pinned alias blocks reuse as appropriate. Historical projection membership is never rewritten.

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

This checkpoint intentionally does not implement arbitrary semantic Timeline search, unrestricted pronoun/coreference resolution, model-selected history or referents, embedding/vector lookup, semantic alias/reference matching, model-generated aliases, latest-open-loop-wins behavior, automatic expiry/supersession, background work, proactive reminders/contact, or conversion of open-loop content into MemoryClaim.

The bounded implementation proves durable conversational continuity and deterministic addressability while preserving the distinction between unresolved dialogue and every stronger kind of state.
