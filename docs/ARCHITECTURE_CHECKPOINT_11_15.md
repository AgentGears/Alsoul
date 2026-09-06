# Architecture Checkpoint — Decisions 11.A through 15.B

**Status:** Converged foundation checkpoint
**Publication:** GitHub-safe

This checkpoint advances the public semantic model from Decision 10.B through the boundary required to begin F4 implementation.

## Decision 11.A — One Person across many presences

`CompanionPerson` remains the sole durable identity across surfaces, channels, devices, and embodiments.

```text
CompanionPerson
≠ SurfaceBinding
≠ ChannelBinding
≠ EmbodimentBinding

Relationship
≠ Thread
≠ Channel
```

Inbound routing resolves trusted destination binding → CompanionPerson and trusted sender identity → CounterpartPerson before an InteractionEvent is admitted. Historical events retain presence bindings for attribution without allowing infrastructure identity to redefine Person or Relationship.

## Decision 11.B — Modality acquisition and presentation truth

Rich modality separates source capture, derived representation, semantic interaction/output, presentation rendering, actual presentation, and stronger reception evidence.

```text
received media ≠ transcript
transcript ≠ admitted proposition
adopted ≠ rendered ≠ presented
presented ≠ read/heard ≠ understood
```

Streaming presentation records the exact presented extent. A canonical counterpart input that socially interrupts an active presentation terminates that presentation; the unpresented remainder is not automatically resumed.

## Decision 12.A — PresentationProfile, AffectState, InteractionPolicy

`PresentationProfile` is durable versioned presentation configuration outside `SelfModel`. `AffectState` is bounded source-linked current interactional/appraisal state and is not stable personality. `InteractionPolicy` is an immutable derived control snapshot for one cognition/output situation.

```text
SelfModel
≠ PresentationProfile
≠ AffectState
≠ InteractionPolicy
```

Style may shape truthful expression. It cannot change epistemic state, memory, authority, external effect, commitment, or presentation truth.

## Decision 13.A — ConversationOpenLoop

`ConversationOpenLoop` is durable relationship-scoped unresolved conversational dependency.

```text
ConversationOpenLoop
≠ MemoryClaim
≠ DelegatedTask
≠ Commitment
≠ Trigger
```

Loop lifecycle is append-oriented and distinguishes resolved, cancelled, superseded, and expired. An unfinished conversational loop does not authorize background work or proactive follow-up.

## Decision 14.A — Whole-system hydration and recovery

Recovery is deterministic reconstruction from Alsoul-owned durable state, not restoration of model/provider runtime.

Operation-specific readiness barriers govern ingress admission, cognition, work continuation, effectful execution, and presentation. Canonical identity/Self and required Relationship integrity are hard blockers; optional derived domains may degrade only the operations whose truth depends on them.

```text
persistence ≠ recoverability
recoverability ≠ hydration
provider session ≠ CompanionPerson
```

Recovery resumes from the furthest trustworthy durable stage.

## Decision 15.A — F4 physical persistence

The F4 walking skeleton uses a transactional relational store. Identity-bearing Self and Relationship state use immutable complete revisions plus current heads. Timeline, evidence, claims, source captures, WorldResults, ContextProjections, generated/adopted outputs, and presentation history are immutable or append-oriented.

External calls do not occur inside long-lived database transactions. Each semantic admission boundary commits a small valid durable stage.

## Decision 15.B — F4 application services and recovery state

Canonical F4 state advances only through typed semantic application services. Generic persistence mutation is not an application API.

Database-command retries use stable operation identity. New external acquisition creates a new Observation. New model execution creates a new ModelInvocation. Output adoption is fenced by a semantic OutputTarget and first-party presentation by one Timeline event per CompanionOutput.

Response recovery state is derived from canonical rows rather than stored as an authoritative mutable turn-status record.

## Implementation boundary

The first executable slice intentionally implements only:

```text
persistent Person/Self/Relationship
canonical text Timeline
one factual evidence-grounded personal memory
fresh world Investigation/Observation/Capture/WorldResult
immutable ContextProjection
ModelInvocation / GeneratedOutput
CompanionOutput adoption
first-party text presentation
complete runtime reconstruction
```

Effectful Actions, durable Tasks, proactivity, rich modality, affect, and open-loop persistence remain outside the F4 code path even though their semantic boundaries are fixed above.
