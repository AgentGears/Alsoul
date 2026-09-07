# F4 Interaction Purpose Gate

## Status

This checkpoint prevents canonical counterpart input from being forced through a semantic path that the input does not justify.

F4 now distinguishes three bounded implemented purposes:

```text
MEMORY_STATEMENT
WORLD_QUESTION
CONVERSATIONAL_RESPONSE
```

Everything else is `UNSUPPORTED` and fails closed after trusted ingress has preserved the input in canonical history.

## Core invariants

```text
canonical input ≠ interaction-purpose classification
interaction classification ≠ model authority
memory statement ≠ fresh-world question ≠ conversational response
memory admission ≠ response obligation
conversation ≠ fresh-world investigation
conversation ≠ memory admission
no CompanionOutput ≠ failed interaction
surface notice ≠ CompanionOutput
surface notice ≠ presented Timeline event
unsupported input ≠ inferred intent
```

The gate exists to make the narrow F4 implementation honest about what work an input actually requires. It is not a general natural-language router.

## Canonical order

Interaction-purpose classification occurs only after trusted ingress has committed the counterpart input:

```text
trusted first-party ingress
↓
COUNTERPART_INPUT InteractionEvent
↓
F4InteractionPurposeGate
├── MEMORY_STATEMENT
│   ↓
│   evidence-grounded memory admission
│   ↓
│   stop
│
├── CONVERSATIONAL_RESPONSE
│   ↓
│   source-free ContextProjection
│   ↓
│   ModelInvocation / GeneratedOutput
│   ↓
│   conversational adoption
│   ↓
│   CompanionOutput
│   ↓
│   first-party presentation acceptance
│   ↓
│   COMPANION_PRESENTED_OUTPUT
│
└── WORLD_QUESTION
    ↓
    recover eligible personal memory
    ↓
    Investigation
    ↓
    Observation / WorldSourceCapture / EvidenceItem
    ↓
    WorldResult
    ↓
    ContextProjection
    ↓
    ModelInvocation / GeneratedOutput
    ↓
    CompanionOutput
    ↓
    first-party presentation acceptance
    ↓
    COMPANION_PRESENTED_OUTPUT
```

This ordering matters. The transport or browser does not classify raw input before canonical admission, and the model does not decide which semantic path should run.

## Deterministic bounded classification

`F4InteractionPurposeGate` is provider-independent and read-only. It loads one immutable canonical `COUNTERPART_INPUT`, validates that the event belongs to the expected counterpart/relationship and exact surface/channel route, and classifies only the event's canonical text.

The current classifier recognizes a deliberately small grammar.

A supported memory statement includes bounded forms such as:

```text
My machine has 16 GB RAM.
My computer has 16 GB of memory.
Actually, my machine has 32 GB RAM.
```

A supported fresh-world question includes bounded forms such as:

```text
Would the current software run on my machine?
Does my computer meet the current software memory requirements?
```

A supported conversational response includes self-contained social forms such as:

```text
Hello.
Thanks.
How are you?
Goodbye.
```

Inputs outside those contracts are not handed to a model to guess intent. For example:

```text
Tell me a joke.
What is the weather?
Tell me what you think about this.
My machine has 16 GB RAM; would it run?
```

remain canonical counterpart history but produce `INTERACTION_PURPOSE_UNSUPPORTED` at the high-level F4 interaction boundary.

The contextual phrase `this` remains unsupported because this checkpoint does not yet define a bounded prior-history selection policy for conversational reference resolution.

```text
unknown purpose ≠ model-selected purpose
```

## Memory-only interaction

For `MEMORY_STATEMENT`, the high-level configured runtime performs only the governed memory path:

```text
COUNTERPART_INPUT
↓
classification = MEMORY_STATEMENT
↓
candidate
↓
proposal
↓
current-claim validation under admission fence
↓
EvidenceItem + Claim admission
↓
return memory outcome
```

A successful memory-only interaction does not create an Investigation, ContextProjection, ModelInvocation, GeneratedOutput, CompanionOutput, or `COMPANION_PRESENTED_OUTPUT` event. The durable semantic result is the admitted memory itself.

Exact transport/source replay recovers the same canonical input and admitted Claim/Evidence state without provider work or duplicate memory admission.

## Conversational interaction

For `CONVERSATIONAL_RESPONSE`, the high-level runtime builds a minimal response projection containing the pinned Self revision, Relationship revision, Timeline frontier, and current input while selecting no personal Claim or WorldResult proposition.

```text
CONVERSATIONAL_RESPONSE
↓
ContextProjection
    personal_context_items = []
    world_context_items = []
↓
ModelInvocation
↓
GeneratedOutput
    exactly one COMPANION_EXPRESSION
    source_ref = null
↓
explicit conversational adoption
↓
CompanionOutput
↓
presentation acceptance
↓
presented Timeline event
```

This path performs no fresh-world acquisition and no memory admission. A source-free expression is Companion-owned wording, not evidence-backed world or memory provenance.

See [F4 Conversational Response Path](F4_CONVERSATIONAL_RESPONSE.md) for the complete contract.

## World-question interaction

For `WORLD_QUESTION`, the gate delegates to the recovery-safe checked response coordinator.

```text
WORLD_QUESTION
↓
current admitted personal memory
+
fresh checked world result
↓
ContextProjection
↓
model generation
↓
CompanionOutput adoption
↓
presentation acceptance
↓
presented Timeline event
```

A prior memory-only interaction can establish the remembered personal fact without forcing a reply, and a later world question can recover that fact after complete process replacement and use it as eligible personal context.

## High-level and low-level runtime boundaries

`ConfiguredFoundationRuntime.interact` is the high-level F4 interaction boundary. Both the process-facing host and local first-party surface use this boundary.

`ConfiguredFoundationRuntime.respond` remains the lower-level checked `WORLD_QUESTION` response/recovery primitive. It now verifies the canonical input purpose and rejects a memory or conversational input before provider work.

```text
interact = select and execute one implemented F4 semantic path
respond  = execute/resume an already-selected checked WORLD_QUESTION path
```

## Surface acknowledgement is not CompanionPerson speech

A memory-only interaction may use a deterministic operational `surface_notice`, such as:

```text
Memory updated
```

That notice is not adopted conversational content. It does not create a `CompanionOutput`, pass through presentation, or enter canonical Timeline history as `COMPANION_PRESENTED_OUTPUT`.

A conversational response is different: it must cross model-generation, adoption, and first-party presentation boundaries before the browser renders it as Companion speech.

```text
surface acknowledgement ≠ CompanionPerson utterance
```

## Unsupported interaction

`UNSUPPORTED` means only that the current F4 executable slice does not implement a semantic path for the input.

Trusted ingress still happens first, so the counterpart input remains historical Timeline evidence. The high-level interaction then fails closed before provider work.

The implementation does not guess a nearby supported intent, send the input to a model for route selection, silently start fresh-world work, admit unsupported text as memory, or manufacture a CompanionOutput to hide the limitation.

## Recovery and idempotency

The purpose gate introduces no mutable interaction-status aggregate. Classification is a deterministic derivation from immutable canonical input.

```text
same canonical input
↓
same bounded classification
```

Memory replay remains provider-free. Conversational replay and checked-response replay use the existing canonical response recovery graph so committed projection, generation, adoption, and presentation stages are recovered rather than duplicated.

## Acceptance contract

The executable suite must prove at least:

1. supported memory statements classify as `MEMORY_STATEMENT`;
2. supported current-world questions classify as `WORLD_QUESTION`;
3. bounded self-contained social inputs classify as `CONVERSATIONAL_RESPONSE`;
4. contextual/deictic, arbitrary-world, mixed, and otherwise unsupported utterances remain `UNSUPPORTED`;
5. classification is derived from canonical counterpart Timeline state and writes no semantic state;
6. route mismatch fails closed before semantic continuation;
7. a memory-only interaction admits one evidence-grounded memory without unrelated provider work;
8. a conversational interaction produces one source-free Companion expression without Investigation or WorldResult;
9. conversational replay does not duplicate model generation, adoption, presentation, or Timeline output;
10. a later world question can recover previously admitted memory after complete runtime/surface recomposition;
11. the process-facing host and local surface use the same high-level purpose gate;
12. the lower-level checked-response path rejects non-world-question input before provider work; and
13. memory surface acknowledgement remains operational UI status rather than CompanionPerson output.

## Scope boundary

This checkpoint does not implement general conversational intent classification, model-selected routing, mixed memory-and-question utterances, arbitrary small talk, deictic prior-turn resolution, general question answering, arbitrary fresh-world questions, general memory extraction, external Actions, delegated work, or proactive initiation.

The gate remains intentionally as narrow as the F4 implementation itself.