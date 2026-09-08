# Architecture Checkpoint — Decisions 11.A through 15.B

**Status:** Converged foundation checkpoint
**Publication:** GitHub-safe

This checkpoint advances the public semantic model from Decision 10.B through the boundary required for the executable F4 foundation.

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

The executable F4 implementation includes one deliberately bounded `DECISION` open-loop kind. Its opening and terminal closure are durable append-oriented records; an unqualified bounded resume may select exactly one unresolved decision loop by relationship. Ambiguity fails closed rather than using latest-wins selection. See [F4 Conversation Open Loop](F4_CONVERSATION_OPEN_LOOP.md).

## Decision 13.B — Targetable open-loop references

`ConversationOpenLoop.open_loop_id` remains canonical loop identity. Human-addressable routing is represented separately by immutable source-grounded `ConversationOpenLoopReference` state.

```text
open_loop_id
≠ open_loop_reference_id
≠ canonical_reference_key
≠ current-input selector
```

F4 `DECISION` loops use one versioned `DECISION_OPTION_PAIR` reference admitted with the loop. Normalization is deliberately mechanical: Unicode normalization, whitespace normalization, case folding, and order-independent option-pair canonicalization. Semantic similarity, embeddings, paraphrase expansion, model interpretation, recency, and latest-wins selection do not participate.

A later bounded directive produces a selector. Unqualified selectors require exactly one active decision loop; explicit selectors require exactly one active loop with an exact durable reference match. Zero explicit matches fail not-found and multiple matches fail ambiguous. The same deterministic selection layer may govern bounded resume, resolve, and cancel operations.

Successful selection is pinned into immutable `ContextProjection` selector provenance. The model receives only the host-resolved loop. Reuse preserves the original selector semantics: unqualified selection requires global active-loop uniqueness while explicit selection requires uniqueness only among active loops matching its pinned reference. See [F4 Targetable Conversation Open Loop](F4_TARGETABLE_CONVERSATION_OPEN_LOOP.md).

## Decision 13.C — Explicit user-authored open-loop aliases

`ConversationOpenLoopAlias` is an immutable durable relationship-scoped address explicitly assigned by the counterpart to one already-resolved `ConversationOpenLoop`. Alias identity, source-derived reference identity, loop identity, and current-input selectors remain separate.

```text
ConversationOpenLoop
≠ ConversationOpenLoopReference
≠ ConversationOpenLoopAlias
≠ selector
```

F4 aliases use `USER_LABEL_V1`, which performs only mechanical Unicode normalization, whitespace normalization, and case folding. Model-generated titles, inferred topics, embeddings, semantic similarity, and recency cannot create or resolve aliases.

Alias admission first resolves exactly one active loop under an existing deterministic selector and then applies a relationship-scoped write fence. One canonical active alias key may address at most one active `DECISION` loop in a relationship. The same loop may have multiple aliases; repeated assignment of the same canonical alias to the same loop reuses the existing alias.

Alias removal and rename are append-oriented and separate from loop closure. Rename retires the old alias and creates or reuses a replacement alias; closing a loop does not erase alias history and retiring an alias does not close the loop.

Alias resume/resolve/cancel uses exact active alias equality. Successful alias selection is pinned into immutable `ContextProjection` provenance. Reuse requires the selected loop to remain active and the pinned alias to remain an unretired unique active address; unrelated loops do not invalidate the selection. Explicit alias context uses renderer contract `f4-renderer-v5`. Migration does not fabricate aliases for older loops because older state contains no canonical user-authored alias-assignment contract. See [F4 Conversation Open Loop Alias](F4_CONVERSATION_OPEN_LOOP_ALIAS.md).

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

The F4 walking skeleton uses a transactional relational store. Identity-bearing Self and Relationship state use immutable complete revisions plus current heads. Timeline, evidence, claims, source captures, WorldResults, ContextProjections, generated/adopted outputs, presentation history, ConversationOpenLoop lifecycle, source-derived references, user-authored aliases, and selector provenance are immutable or append-oriented.

External calls do not occur inside long-lived database transactions. Each semantic admission boundary commits a small valid durable stage.

## Decision 15.B — F4 application services and recovery state

Canonical F4 state advances only through typed semantic application services. Generic persistence mutation is not an application API.

Database-command retries use stable operation identity. New external acquisition creates a new Observation. New model execution creates a new ModelInvocation. Output adoption is fenced by a semantic OutputTarget and first-party presentation by one Timeline event per CompanionOutput.

Response recovery state is derived from canonical rows rather than stored as an authoritative mutable turn-status record. Open-loop-aware projection reuse revalidates the exact selector semantics pinned by the immutable projection before another provider execution.

## Implementation boundary

The executable slice currently implements:

```text
persistent Person/Self/Relationship
canonical text Timeline
one factual evidence-grounded personal memory
fresh world Investigation/Observation/Capture/WorldResult
immutable ContextProjection
ModelInvocation / GeneratedOutput
CompanionOutput adoption
first-party text presentation
bounded conversational response
bounded immediate-prior Timeline context
bounded relationship-scoped ConversationOpenLoop
exact targetable DECISION source references
explicit counterpart-authored DECISION aliases
complete runtime reconstruction
```

Effectful Actions, durable Tasks, proactivity, rich modality, and affect remain outside the F4 code path. ConversationOpenLoop remains deliberately narrow: generic semantic history retrieval, semantic reference/alias matching, automatic expiry/supersession, background work, and proactive contact remain outside the slice.
