# F4 Conversational Response Path

## Status

This checkpoint defines the bounded conversational response path in the executable F4 interaction slice.

The purpose remains deliberately narrower than general conversation. F4 recognizes a small class of self-contained social utterances and a still-smaller class of contextual utterances whose reference can be resolved mechanically against exactly one immediately preceding presented exchange.

The implemented purpose is:

```text
CONVERSATIONAL_RESPONSE
```

It sits beside:

```text
MEMORY_STATEMENT
WORLD_QUESTION
CONVERSATIONAL_RESPONSE
UNSUPPORTED
```

## Core invariants

```text
conversation ≠ fresh-world investigation
conversation ≠ memory admission
interaction classification ≠ model authority
provider session ≠ relationship continuity
ContextProjection ≠ canonical history
Timeline history ≠ MemoryClaim
selected prior event ≠ admitted personal fact
selected prior Companion output ≠ canonical factual truth
reference resolution ≠ unrestricted transcript injection
GeneratedOutput ≠ CompanionOutput
CompanionOutput ≠ presentation
response generation ≠ canonical factual belief
source-free expression ≠ evidence-backed proposition
```

The model is used only after Alsoul has already selected the bounded conversational path from canonical counterpart input.

## Bounded classification

`F4InteractionPurposeGate` remains deterministic, provider-independent, and read-only. Classification occurs after trusted ingress has committed the `COUNTERPART_INPUT` to the canonical Timeline.

Self-contained forms include:

```text
Hello.
Hi.
Hey there.
Thanks.
Thank you.
How are you?
Goodbye.
See you later.
```

F4 also recognizes a narrow contextual grammar:

```text
What do you think about that?
What do you think of it?
Tell me what you think about that.
```

These forms do not authorize model-selected history retrieval. They only request the bounded prior-Timeline selection contract described below.

Inputs whose meaning requires broader reference resolution, arbitrary question answering, or another unimplemented semantic path remain `UNSUPPORTED`. Examples include:

```text
Tell me a joke.
What is the weather?
Compare what I said earlier this week with what I said last month.
```

## Canonical path

A supported conversational interaction follows:

```text
trusted first-party ingress
↓
COUNTERPART_INPUT InteractionEvent
↓
F4InteractionPurposeGate
↓
CONVERSATIONAL_RESPONSE
↓
ContextProjection
    current Self revision
    current Relationship revision
    current Timeline frontier
    current input event
    optional bounded prior Timeline exchange
    no projected PersonClaim
    no projected WorldResult
↓
ModelInvocation
↓
GeneratedOutput
↓
conversational output validation/adoption
↓
CompanionOutput
↓
first-party presentation acceptance
↓
COMPANION_PRESENTED_OUTPUT
```

No `Investigation`, `Observation`, `WorldSourceCapture`, `WorldResult`, or memory-admission transaction is created merely because a conversational response is requested.

## Context boundary

For a self-contained conversational form, the projection binds cognition to:

```text
CompanionPerson / Self revision
RelationshipState revision
current counterpart input
current relationship Timeline frontier
```

and carries:

```text
personal_context_items = []
world_context_items = []
selected_event_refs = [current_input]
```

For a bounded contextual form, the only accepted prior-history shape is:

```text
I1  COUNTERPART_INPUT
↓
I2  COMPANION_PRESENTED_OUTPUT
    reply_to_event_id = I1
↓
I3  current COUNTERPART_INPUT
```

with exact adjacency:

```text
I1.timeline_seq = I3.timeline_seq - 2
I2.timeline_seq = I3.timeline_seq - 1
I3.timeline_seq = current Timeline frontier
```

The projection then carries:

```text
selected_event_refs = [I1, I2, I3]
timeline_context_selection = IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE
personal_context_items = []
world_context_items = []
```

The prior counterpart input must belong to the same conversation binding as the current input, and the prior exchange must use the same SurfaceBinding and ChannelBinding. The prior presented output must be the actual CompanionPerson presentation replying to the adjacent counterpart input.

If that exact shape is unavailable, the interaction fails closed before model execution. It does not fall back to a transcript window, semantic search, or model-selected context.

```text
not projected ≠ forgotten
not projected ≠ deleted
not projected ≠ false
historical interaction context ≠ admitted memory
```

See [F4 Prior-Timeline Context Selection](F4_PRIOR_TIMELINE_CONTEXT.md) for the detailed selection and recovery contract.

## Provider rendering

A self-contained conversational projection sends no prior-history field.

A contextual projection adds a separate provider field:

```text
prior_timeline_context {
    selection_policy: IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE
    events: [
        prior counterpart input,
        prior presented Companion output
    ]
}
```

Those events remain historical interaction context. They are not rendered as `PersonClaim`, `MemoryClaim`, or `WorldResult`, and they do not become source attribution for the new response.

Changing this provider rendering contract advances the renderer identity. New invocations use the updated renderer version while existing durable invocations remain historical records of the renderer that actually ran.

## Conversational expression contract

The configured model contract uses one bounded epistemic kind:

```text
COMPANION_EXPRESSION
```

The model must return exactly one non-empty segment:

```text
FoundationResponseDraft {
    segments: [
        {
            epistemic_kind: COMPANION_EXPRESSION
            text: ...
            source_ref: null
        }
    ]
}
```

`COMPANION_EXPRESSION` is Companion-owned conversational wording. It is not a claim that Alsoul checked the world, remembered an admitted proposition, or derived an evidence-backed fact.

The absence of a source reference remains mandatory even when prior Timeline context was selected. `source-free` means the expression is not claiming Claim/WorldResult provenance; it does not mean the invocation had no conversational history context.

## Adoption boundary

A valid model return is still only a `GeneratedOutput`.

The conversational path validates that:

1. the OutputTarget is the one `FINAL_RESPONSE` slot for the current input;
2. the GeneratedOutput came from the exact current ContextProjection;
3. the projection contains no personal or world proposition items;
4. the semantic payload contains exactly one source-free `COMPANION_EXPRESSION`;
5. generated visible text exactly matches the canonical rendering of that payload; and
6. the semantic OutputTarget has not already been filled.

Only then is one `CompanionOutput` admitted.

```text
model text
≠ adopted companion speech
```

Selected prior Timeline events do not weaken the checked-response output contract and do not acquire factual source authority through conversational adoption.

## Presentation boundary

Conversational output uses the same first-party presentation contract as the checked response path:

```text
CompanionOutput
+ exact SurfaceBinding
+ exact ChannelBinding
↓
stable semantic presentation key
↓
first-party sink acceptance
↓
COMPANION_PRESENTED_OUTPUT
```

The canonical Timeline advances only after the sink positively accepts the exact adopted content and digest.

```text
adopted ≠ presented
presented ≠ read/heard/understood
```

## Recovery

The conversational path reuses the existing response recovery graph:

```text
INPUT_ADMITTED
PROJECTION_READY
MODEL_ATTEMPT_UNRESOLVED
GENERATED
ADOPTED
PRESENTED
```

For contextual conversation, selected prior events are immutable projection members. Recovery does not perform a fresh history lookup after the ContextProjection has committed.

```text
ContextProjection [I1, I2, I3]
↓
process loss
↓
recover same ContextProjection
↓
reuse exact selected events while projection remains reusable
```

A durable `GeneratedOutput` is recovered rather than regenerated. A process loss after sink acceptance but before canonical Timeline presentation uses the existing idempotent presentation key and does not create a second semantic output.

## High-level and lower-level routing

`ConfiguredFoundationRuntime.interact` is the high-level interaction boundary. It selects among the implemented F4 purposes before provider work.

The lower-level `ConfiguredFoundationRuntime.respond` remains specifically the checked `WORLD_QUESTION` response/resumption primitive and rejects conversational input before world or model provider work.

```text
interact
    = bounded purpose selection + execution

respond
    = already-selected checked WORLD_QUESTION execution/recovery
```

## Local first-party surface

The local browser surface uses the same high-level runtime boundary.

For a supported conversational interaction:

- the browser does not classify the input;
- canonical input is admitted first;
- deterministic contextual selection, when required, occurs inside the semantic service boundary;
- no operational `surface_notice` is substituted for Companion speech;
- one adopted CompanionOutput passes through presentation acceptance; and
- accepted text appears as actual Companion output and canonical presented Timeline history.

This differs intentionally from a memory-only interaction, where deterministic surface status may acknowledge local operation completion without fabricating Companion speech.

## Acceptance contract

The executable suite must prove at least:

1. bounded greetings, thanks, check-ins, farewells, and the narrow contextual grammar classify as `CONVERSATIONAL_RESPONSE`;
2. unsupported forms do not silently widen into conversation;
3. self-contained conversation projects current input only;
4. contextual conversation projects exactly the immediately prior completed exchange plus current input;
5. contextual selection does not cross conversation, surface, or channel boundaries;
6. missing prior exchange fails before provider execution;
7. conversational execution creates no Investigation, Observation, or WorldResult;
8. ContextProjection contains no personal or world proposition items;
9. prior Timeline context is rendered separately from personal/world proposition context;
10. the configured model contract requires exactly one `COMPANION_EXPRESSION` segment;
11. conversational source attribution is rejected;
12. GeneratedOutput remains distinct from CompanionOutput adoption;
13. first-party presentation remains distinct from adoption;
14. exact replay after presentation does not repeat generation or presentation;
15. process loss after durable contextual generation recovers the same projection without history reselection or regeneration;
16. the lower-level checked response primitive rejects conversational input before provider work; and
17. complete local surface/runtime recomposition preserves durable Person, Relationship, projection/output, and Timeline boundaries.

## Scope boundary

This checkpoint does not implement:

- general conversational intent classification;
- arbitrary small talk generation beyond the bounded grammar;
- arbitrary pronoun or entity-coreference resolution;
- generic prior-history windows;
- semantic search over Timeline history;
- cross-thread contextual references;
- cross-channel contextual references;
- arbitrary question answering;
- model-selected memory admission;
- automatic use of historical Timeline text as memory;
- fresh-world acquisition for conversational inputs;
- external Actions;
- delegated work;
- schedules or proactive contact; or
- affect-state persistence.

The path now proves both ordinary source-free social response and one mechanically bounded form of conversational continuity without collapsing history into memory or evidence.
