# F4 Prior-Timeline Context Selection

## Status

This checkpoint adds the first bounded conversational continuity mechanism to the executable F4 slice.

It does **not** add a generic transcript window or unrestricted pronoun resolution. It permits only a small deterministic contextual grammar, such as:

```text
What do you think about that?
What do you think of it?
Tell me what you think about that.
```

When one of those forms is the current canonical input, Alsoul may project exactly one immediately preceding completed exchange into the next cognition invocation.

## Core invariants

```text
Timeline history ≠ MemoryClaim
selected prior event ≠ admitted personal fact
selected prior Companion output ≠ canonical factual truth
conversation context ≠ canonical history
prior-event selection ≠ model routing authority
reference resolution ≠ unrestricted transcript injection
not selected ≠ forgotten
historical context ≠ evidence-backed proposition
```

The model does not decide what `that` or `it` refers to. The host-owned semantic policy either resolves the bounded reference mechanically or fails closed before provider execution.

## Selection contract

For a contextual current input `I3`, the only accepted F4 shape is:

```text
I1  COUNTERPART_INPUT
↓
I2  COMPANION_PRESENTED_OUTPUT
    reply_to_event_id = I1
↓
I3  COUNTERPART_INPUT
    bounded contextual grammar
```

The Timeline sequence must be exactly adjacent:

```text
I1.timeline_seq = I3.timeline_seq - 2
I2.timeline_seq = I3.timeline_seq - 1
I3.timeline_seq = current Timeline frontier
```

`I1`, `I2`, and `I3` must belong to the same RelationshipState. `I1` must belong to the same conversation binding as `I3`, and the prior input/output must use the same SurfaceBinding and ChannelBinding as the current input. The presented output must be the CompanionPerson's actual canonical presented response to `I1`.

If any of those conditions fail, the contextual interaction does not fall back to model-selected history.

## ContextProjection

The contextual projection remains a normal immutable `ContextProjection` with:

```text
purpose = RESPOND_TO_INTERACTION
current_input_event_id = I3
source_timeline_frontier = I3.timeline_seq
selected_event_refs = [I1, I2, I3]
personal_context_items = []
world_context_items = []
```

The manifest also records the bounded selection policy:

```text
IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE
```

The existing `context_projection_event` relation is sufficient; no mutable conversation-context aggregate is introduced.

## Provider rendering

The provider receives the current input separately and, only for a contextual projection, receives:

```text
prior_timeline_context {
    selection_policy: IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE
    events: [
        I1 counterpart input,
        I2 presented Companion output
    ]
}
```

These events are historical interaction context. They are **not** rendered as `PersonClaim`, `MemoryClaim`, `WorldResult`, or source attribution for the new response.

The generated response therefore remains one source-free:

```text
COMPANION_EXPRESSION
```

with `source_ref = null`.

`source-free` here means that the response is not asserting Claim/WorldResult provenance. It does not mean the invocation had no selected conversational history.

Provider rendering is versioned. The current executable renderer identity is `f4-renderer-v3`; it retains this `prior_timeline_context` contract while also supporting the later bounded ConversationOpenLoop rendering contract. Renderer identity changes whenever the provider-context structure changes.

## Recovery

The selected events are immutable projection members. Process loss does not trigger a fresh history search.

```text
ContextProjection committed
↓
process loss
↓
recover same projection
↓
reuse exact [I1, I2, I3] selection while projection remains reusable
```

If a `GeneratedOutput` is already durable, recovery reuses it and performs no history reselection or model regeneration.

The normal projection reuse fence still requires the pinned Self revision, Relationship revision, and Timeline frontier to remain current before another provider invocation can start.

## Failure semantics

A bounded contextual form can fail with no provider work when:

- no immediately preceding completed exchange exists;
- the preceding pair is not exactly `COUNTERPART_INPUT → COMPANION_PRESENTED_OUTPUT`;
- the presented output does not reply to the adjacent counterpart input;
- the prior counterpart input belongs to another conversation binding;
- the prior exchange used another surface or channel; or
- the contextual input is no longer the Timeline frontier.

The current counterpart input remains canonical history because trusted ingress occurred first.

```text
canonical input preserved
+
context unavailable
≠ guessed reference
≠ transcript fallback
≠ model-selected history
```

## Acceptance contract

The executable suite must prove at least:

1. the bounded contextual forms classify as `CONVERSATIONAL_RESPONSE`;
2. a successful contextual response projects exactly the prior counterpart input, its presented Companion response, and the current input;
3. provider context carries the prior exchange separately from personal/world proposition context;
4. contextual conversation performs no Investigation or WorldResult admission;
5. selected prior Companion output is not given Claim/WorldResult source authority;
6. no prior completed exchange fails closed before model invocation;
7. conversation-boundary mismatch fails closed;
8. surface/channel-boundary mismatch fails closed;
9. the current contextual input must be the Timeline frontier;
10. process loss after durable generation recovers the same projection without reselection or regeneration; and
11. the current model invocation records the renderer identity required by the provider-context contract.

## Scope boundary

This checkpoint does not implement:

- arbitrary pronoun or entity-coreference resolution;
- `last N messages` transcript injection;
- semantic search over Timeline history;
- memory inference from prior conversational text;
- using prior Companion speech as factual evidence;
- cross-thread contextual reference resolution for this immediate-prior mechanism;
- cross-channel contextual fallback;
- model-selected context retrieval.

A later bounded relationship-scoped ConversationOpenLoop mechanism may resume an explicitly admitted unresolved conversational dependency across a thread change. That capability does not widen this immediate-prior selection contract into generic history retrieval.

This checkpoint exists to establish one mechanically honest bridge from a current conversational reference to exact canonical prior interaction before widening conversational continuity further.
