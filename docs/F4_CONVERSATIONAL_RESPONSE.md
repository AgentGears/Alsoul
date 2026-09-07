# F4 Conversational Response Path

## Status

This checkpoint adds the first bounded conversational response path to the executable F4 interaction slice.

The purpose is deliberately narrower than general conversation. F4 now recognizes a small class of self-contained social utterances such as greetings, thanks, simple check-ins, and farewells without misrouting them into fresh-world investigation or memory admission.

The implemented purpose is:

```text
CONVERSATIONAL_RESPONSE
```

It sits beside the existing bounded purposes:

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
GeneratedOutput ≠ CompanionOutput
CompanionOutput ≠ presentation
response generation ≠ canonical factual belief
source-free expression ≠ evidence-backed proposition
```

The model is used only after Alsoul has already selected the bounded conversational path from a canonical counterpart input.

## Bounded classification

`F4InteractionPurposeGate` remains deterministic, provider-independent, and read-only. Classification occurs after trusted ingress has committed the `COUNTERPART_INPUT` to the canonical Timeline.

The conversational grammar currently recognizes bounded self-contained forms including:

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

This is not a general natural-language conversation router. Inputs whose meaning requires broader reasoning, prior-turn reference resolution, arbitrary question answering, or another unimplemented semantic path remain `UNSUPPORTED`.

Examples intentionally outside this checkpoint include:

```text
Tell me a joke.
What is the weather?
Tell me what you think about this.
```

The last example is deliberately unsupported because this checkpoint does not yet project a bounded prior conversational-history window for deictic references such as `this`.

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

The current conversational projection is intentionally minimal. It binds cognition to:

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
```

This does not mean the relationship has no history or memory. It means those states were not selected into this invocation.

```text
not projected ≠ forgotten
not projected ≠ deleted
not projected ≠ false
```

The minimal projection prevents this checkpoint from treating old Timeline text as admitted memory or fresh world truth merely to make a social response feel contextual.

## Conversational expression contract

The configured model contract introduces one bounded epistemic kind:

```text
COMPANION_EXPRESSION
```

For the current conversational path the model must return exactly one non-empty segment:

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

The absence of a source reference is mandatory. A provider response that attaches a Claim, WorldResult, or arbitrary source reference to a conversational expression is rejected.

## Adoption boundary

A valid model return is still only a `GeneratedOutput`.

The conversational path uses a typed adoption service to validate that:

1. the OutputTarget is the one `FINAL_RESPONSE` slot for the current input;
2. the GeneratedOutput came from the exact current ContextProjection;
3. the projection contains no personal or world proposition items;
4. the semantic payload contains exactly one source-free `COMPANION_EXPRESSION`;
5. the generated visible text exactly matches the canonical rendering of that payload; and
6. the semantic OutputTarget has not already been filled.

Only then is one `CompanionOutput` admitted.

```text
model text
≠ adopted companion speech
```

This specialized validation does not weaken the checked-response output contract. Checked responses still require the established remembered / current-checked / interpretation segmentation and provenance.

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

A process loss after durable generation does not justify regeneration. Recovery finds the existing reusable ContextProjection and GeneratedOutput, validates that the projection is a source-free conversational projection, and continues from the furthest trustworthy durable stage.

A process loss after sink acceptance but before canonical Timeline presentation uses the existing idempotent presentation key and does not create a second semantic output.

## High-level and lower-level routing

`ConfiguredFoundationRuntime.interact` is the high-level interaction boundary. It selects among the implemented F4 purposes before provider work.

The lower-level `ConfiguredFoundationRuntime.respond` remains specifically the checked `WORLD_QUESTION` response/resumption primitive. It now verifies the canonical purpose and rejects a conversational input before world or model provider work.

```text
interact
    = bounded purpose selection + execution

respond
    = already-selected checked WORLD_QUESTION execution/recovery
```

This prevents a caller from bypassing the interaction-purpose gate and forcing a social utterance through the fresh-world pipeline.

## Local first-party surface

The local browser surface uses the same high-level runtime boundary.

For a supported conversational interaction:

- the browser does not classify the input;
- the canonical input is admitted first;
- no operational `surface_notice` is substituted for Companion speech;
- one adopted CompanionOutput passes through presentation acceptance; and
- the accepted text appears as actual companion output and canonical presented Timeline history.

This differs intentionally from a memory-only interaction, where a deterministic surface notice may acknowledge local operation completion without fabricating Companion speech.

## Acceptance contract

The executable suite must prove at least:

1. bounded greetings, thanks, check-ins, and farewells classify as `CONVERSATIONAL_RESPONSE`;
2. contextual/deictic, arbitrary-world, mixed, and unsupported inputs do not silently widen into conversation;
3. conversational execution creates no Investigation, Observation, or WorldResult;
4. the ContextProjection contains no personal or world proposition items;
5. the configured model contract requires exactly one `COMPANION_EXPRESSION` segment;
6. conversational source attribution is rejected;
7. GeneratedOutput remains distinct from CompanionOutput adoption;
8. first-party presentation remains distinct from adoption;
9. exact replay after presentation does not repeat generation or presentation;
10. process loss after durable generation recovers without regeneration;
11. the lower-level checked response primitive rejects conversational input before provider work; and
12. complete local surface/runtime recomposition preserves the same Person, Relationship, input, adopted output, and presented Timeline event.

## Scope boundary

This checkpoint does not implement:

- general conversational intent classification;
- arbitrary small talk generation beyond the bounded grammar;
- deictic reference resolution over prior turns;
- a general prior-history projection policy;
- arbitrary question answering;
- model-selected memory admission;
- automatic use of historical Timeline text as memory;
- fresh-world acquisition for conversational inputs;
- external Actions;
- delegated work;
- schedules or proactive contact; or
- affect-state persistence.

The checkpoint exists to make the first ordinary social response mechanically honest before conversational context selection widens.