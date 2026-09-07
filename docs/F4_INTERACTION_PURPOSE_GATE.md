# F4 Interaction Purpose Gate

## Status

This checkpoint closes the forced-response discontinuity in the first-party F4 interaction slice.

Before this boundary existed, a counterpart statement could be admitted correctly as durable memory and then still fall through into the fixed fresh-world response pipeline. The result was persistence-correct but interaction-semantically wrong: remembering a fact did not itself justify starting an Investigation, invoking a model, adopting a CompanionOutput, or presenting a conversational response.

F4 now distinguishes the two interaction purposes it actually implements:

```text
MEMORY_STATEMENT
WORLD_QUESTION
```

Everything else is `UNSUPPORTED` and fails closed after trusted ingress has preserved the input in canonical history.

## Core invariants

```text
canonical input ≠ interaction-purpose classification
interaction classification ≠ model authority
memory statement ≠ fresh-world question
memory admission ≠ response obligation
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
│   F4MemoryCandidate
│   ↓
│   F4MemoryProposal
│   ↓
│   evidence-grounded memory admission
│   ↓
│   stop
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

`F4InteractionPurposeGate` is provider-independent and read-only. It loads one immutable canonical `COUNTERPART_INPUT`, validates that the event belongs to the expected counterpart/relationship, and classifies only the event's canonical text.

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

Inputs outside those contracts are not handed to a model to guess intent. For example:

```text
Tell me a joke.
What is the weather?
My machine has 16 GB RAM; would it run?
```

remain canonical counterpart history but produce `INTERACTION_PURPOSE_UNSUPPORTED` at the high-level F4 interaction boundary.

This preserves:

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

A successful memory-only interaction does not create:

- an Investigation;
- an Observation;
- a WorldResult;
- a ContextProjection;
- a ModelInvocation;
- a GeneratedOutput;
- a CompanionOutput; or
- a `COMPANION_PRESENTED_OUTPUT` Timeline event.

The absence of those objects is intentional success, not an incomplete response.

The durable semantic result is the admitted memory itself. Exact transport/source replay recovers the same canonical input and admitted Claim/Evidence state without provider work or duplicate memory admission.

## World-question interaction

For `WORLD_QUESTION`, the gate delegates to the existing recovery-safe response coordinator.

The question path remains the F4 walking skeleton:

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

A prior memory-only interaction can therefore establish the remembered personal fact without forcing a reply, and a later world question can recover that fact after complete process replacement and use it as eligible personal context.

## High-level and low-level runtime boundaries

`ConfiguredFoundationRuntime.interact` is the high-level F4 interaction boundary. Both the process-facing host and the local first-party surface use this boundary, so interaction-purpose semantics do not belong to a particular UI.

The older `ConfiguredFoundationRuntime.respond` and `FoundationResponseCoordinator.respond` remain lower-level response/recovery primitives. They resume an interaction that has already been selected for the world-question response path. They are not general intent routers and do not independently reinterpret the input.

This distinction is deliberate:

```text
interact = decide which implemented F4 semantic path applies
respond  = execute/resume the already-selected reactive response path
```

## Surface acknowledgement is not CompanionPerson speech

A memory-only interaction may benefit from lightweight UI feedback so the person can see that the local operation completed. The local surface therefore exposes an operational `surface_notice`, such as:

```text
Memory updated
```

That notice is not adopted conversational content. It does not create a `CompanionOutput`, does not pass through the presentation boundary, and does not enter the canonical Timeline as `COMPANION_PRESENTED_OUTPUT`.

The browser renders the notice in surface status rather than an Alsoul message bubble.

This preserves:

```text
surface acknowledgement ≠ CompanionPerson utterance
```

If Alsoul later needs to conversationally acknowledge remembering something, that will require an explicit cognition/adoption/presentation path rather than reclassifying operational UI text as speech.

## Unsupported interaction

`UNSUPPORTED` means only that the current F4 executable slice does not implement a semantic path for the input.

Trusted ingress still happens first, so the counterpart statement remains historical Timeline evidence. The high-level interaction then fails closed before world acquisition, model generation, or presentation.

The implementation does not:

- guess a nearby supported intent;
- send the input to a model for route selection;
- silently start fresh-world work;
- admit unsupported text as memory; or
- manufacture a CompanionOutput merely to hide the limitation.

## Recovery and idempotency

The purpose gate introduces no mutable interaction-status aggregate. Classification is a deterministic derivation from immutable canonical input.

Therefore after process replacement:

```text
same canonical input
↓
same bounded classification
```

For memory-only replay:

```text
same transport event
↓
same InteractionEvent
↓
MEMORY_STATEMENT
↓
recover same admitted memory
↓
no provider work
```

For a world question, the existing response recovery machinery still resumes from the furthest durable trustworthy stage and preserves the established acquisition/generation/presentation idempotency contracts.

## Acceptance contract

The executable suite must prove at least:

1. supported memory statements classify as `MEMORY_STATEMENT`;
2. supported current-world questions classify as `WORLD_QUESTION`;
3. unsupported and mixed utterances classify as `UNSUPPORTED`;
4. classification is derived from a canonical counterpart Timeline event and writes no semantic state;
5. a memory-only interaction admits one evidence-grounded memory without Investigation, ModelInvocation, CompanionOutput, or presented Timeline output;
6. replaying the same memory-only transport event does not duplicate input, Claim, or Evidence state and still performs no provider work;
7. after complete runtime/surface recomposition, a later world question can recover the admitted memory and use it in the checked response path;
8. the process-facing host uses the same high-level purpose gate rather than bypassing it;
9. unsupported high-level interaction fails before provider work while preserving the canonical input event; and
10. local surface acknowledgement is represented as operational UI status rather than CompanionPerson output.

## Scope boundary

This checkpoint does not implement:

- general conversational intent classification;
- model-selected routing;
- mixed memory-and-question utterances;
- small talk;
- general question answering;
- arbitrary fresh-world questions;
- general memory extraction;
- external Actions;
- delegated work; or
- proactive initiation.

The gate is intentionally as narrow as the F4 implementation itself. Its purpose is to prevent implemented semantic paths from being invoked when the input does not justify them.
