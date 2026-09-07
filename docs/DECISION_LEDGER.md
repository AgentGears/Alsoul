# Alsoul Foundation Decision Ledger

**Status:** Convergence ledger through Decision 15.B  
**Publication:** GitHub-safe

This ledger records decisions treated as converged enough to constrain implementation. Detailed rationale and extended contracts live in the architecture checkpoint and ADRs.

## Decision 01 — Canonical Self identity boundary

`CompanionPerson` identity and `SelfModel` continuity-bearing self-state are distinct. Provider/model configuration, relationship state, presentation configuration, memory, and world state do not define the Person.

## Decision 02.A — Constitutional Self

Foundation constitutional Self contains only:

```text
role = PERSONAL_COMPANION
```

Architecture policy, authority, relationship, autobiography, presentation, memory, and user modeling are excluded.

## Decision 02.B — Slowly Mutable Self

Foundation slowly mutable Self contains only:

```text
preferred_name = "Alsoul"
```

Slowly mutable does not mean automatically learned from behavior or history.

## Decision 02.C — Narrative Self

Narrative Self is a rebuildable revisable interpretation generated from canonical Self plus admissible history/evidence. It is not canonical Self or autobiographical evidence and is not required in F4.

## Decision 02.D — Self revision and hydration

Canonical Self uses immutable complete revisions selected by `SelfHead.current_revision`. Mutations are expected-revision/CAS fenced. Missing or inconsistent current Self fails closed before cognition as that Person.

## Decision 03.A — RelationshipState

`RelationshipState` is the canonical durable relationship edge between one `CompanionPerson` and one `CounterpartPerson`. Thread, surface, channel, embodiment, provider, and credential identities do not define the Relationship.

## Decision 03.B — RelationshipExperience

`RelationshipExperience` is a derived evidence-grounded interpretation of patterns and meaning within one relationship. It is not RelationshipState, PersonModel, AffectState, authority, or mandatory behavior policy.

## Decision 03.C — Relationship revision and recovery

Relationship canonical state uses immutable complete revisions selected by a current head. Recovery resolves an existing relationship; it does not silently get-or-create continuity after state loss.

## Decision 04.A — CounterpartPerson

`CounterpartPerson` is the durable Alsoul-side identity anchor for the counterpart. Descriptive beliefs, credentials, accounts, and authority remain separate. External identity resolution uses explicit bindings rather than model inference.

## Decision 04.B — PersonClaim

A `PersonClaim` is an admitted durable evidence-grounded proposition held by one CompanionPerson about one CounterpartPerson. F4 claims are factual only and require explicit supporting evidence.

## Decision 04.C — PersonModel

`PersonModel` is a rebuildable current structured projection over admissible PersonClaims. It is not an independent mutable profile store and needs no F4 persistence table.

## Decision 04.D — PersonClaim admission and currentness

Claims are immutable after admission. Correction/currentness uses explicit supersession/correction relations rather than mutable `is_current` or latest-timestamp selection. Same-turn corrections are admitted before downstream projection.

## Decision 05.A — EvidenceItem

`EvidenceItem` is an immutable durable anchor over specific recoverable source material. Evidence attachment does not by itself mean the material semantically supports the proposition.

## Decision 05.B — InteractionEvent and canonical Timeline

The Timeline is append-oriented durable shared relationship history with relationship-local monotonic `timeline_seq`. Foundation event kinds are `COUNTERPART_INPUT` and `COMPANION_PRESENTED_OUTPUT`. Generated output is not shared history until presentation.

## Decision 05.C — MemoryClaim

A `MemoryClaim` is an admitted durable evidence-grounded proposition permitted for future recall within explicit memory scope. Historical retention and current context do not imply durable memory admission. F4 physically reuses the factual PersonClaim for both roles.

## Decision 05.D — Memory lifecycle

Memory admission, eligibility, retrieval, and ContextProjection are separate stages. Scope/currentness/support precede relevance. Forgetting is a future additive recall/re-admission fence rather than historical deletion or factual contradiction.

## Decision 06.A — Investigation, Observation, WorldResult

`Investigation` is a bounded inquiry container. `Observation` records actual acquisition and belongs to exactly one Investigation. `WorldResult` is an immutable evidence-backed conclusion derived within the Investigation. Search intent, tool invocation, and model prior knowledge are not observations.

## Decision 06.B — WorldSourceCapture

A successful Observation yields an immutable `WorldSourceCapture` of the material actually acquired. Evidence points to the capture, not a mutable live location. Capture identity is acquisition-specific; content digest is integrity metadata, not identity.

## Decision 06.C — WorldResult derivation and freshness

A WorldResult is admitted only when evidence materially supports the proposition. `CURRENT_CHECKED` use requires recoverable support through `EvidenceItem → WorldSourceCapture → Observation` to the same Investigation. Freshness is use-relative; acquisition timing and explicit `valid_as_of` must fit the current question. Unresolved material contradiction blocks settled checked use.

## Decision 07.A — ContextProjection as cognition boundary

`ContextProjection` is an immutable invocation-scoped provider-independent snapshot of the exact Alsoul-owned state selected for one cognition invocation. It pins canonical revisions/frontiers, source refs, evidence refs, and projection-time epistemic classifications. Provider prompts are renderings, not authority.

## Decision 07.B — Model invocation, adoption, and presentation

```text
ContextProjection
↓
ModelInvocation
↓
GeneratedOutput
↓
adoption
↓
CompanionOutput
↓
presentation
↓
COMPANION_PRESENTED_OUTPUT
```

Generated, adopted, presented, and heard are distinct. F4 adoption also requires user-visible text to equal the canonical rendering of its validated semantic payload.

See [ADR-001](adr/ADR-001_CONTEXT_AND_OUTPUT.md).

## Decision 08.A — Capability, credentials, permission, approval, and Action

Technical capability, credentials, standing permission, operation-specific approval, and semantic Action are separate. A model tool call is only a proposal until host policy and authority checks admit/dispatch it. Credential secrets remain outside cognition.

## Decision 08.B — ExecutionAttempt, idempotency, Effect, and reconciliation

One immutable Action may have multiple ExecutionAttempts. Effect is evidence-grounded external consequence, not transport success. Execution distinguishes `CONFIRMED_EFFECT`, `CONFIRMED_NO_EFFECT`, and `UNKNOWN_EFFECT`; unknown effect survives restart and blocks unsafe blind retry.

See [ADR-002](adr/ADR-002_AUTHORITY_AND_EFFECTS.md).

## Decision 09.A — DelegatedTask, Commitment, Procedure, and Trigger

A conversational request becomes durable work only through task admission. `DelegatedTask` is accepted durable work, `Commitment` is durable obligation, `Procedure` is reusable know-how, and `Trigger` defines when work becomes eligible.

## Decision 09.B — Task lifecycle, TriggerActivation, WorkRun, completion, and cancellation

Task lifecycle is append-oriented. `TriggerActivation` represents one logical activation opportunity. `WorkRun` is one bounded task execution; process/model/action retries do not automatically create new WorkRuns. Task completion requires declared criteria; Commitment discharge is separate. Cancellation fences future work without rewriting history or unknown effects.

## Decision 09.C — WorkArtifact, WorkProduct, delivery, and result ownership

`WorkArtifact` is immutable durable produced/acquired/transformed material. `WorkProduct` is the task-level deliverable adopted from artifacts. Generated content, artifact, product, external save Effect, and Delivery remain distinct.

See [ADR-003](adr/ADR-003_DURABLE_WORK.md).

## Decision 10.A — WorldSignal, Trigger, and proactive initiation

`WorldSignal` records receipt of an external/system stimulus. Signal receipt does not automatically establish Observation, WorldResult, Trigger satisfaction, Permission, or instruction to act. Proactive work and proactive contact are separate.

## Decision 10.B — Signal deduplication, recurring edges, and proactive output idempotency

Signal deduplication follows authoritative source event identity where available, not payload similarity. `TriggerEvaluation` distinguishes `SATISFIED`, `NOT_SATISFIED`, and `UNRESOLVED`. Recurring world-condition triggers are edge-sensitive; temporary uncertainty does not rearm a satisfied trigger. Activation/output identity fences duplicate notifications.

See [ADR-004](adr/ADR-004_PROACTIVITY.md).

## Decision 11.A — One Person across many presences

`CompanionPerson` remains the sole durable identity across `SurfaceBinding`, `ChannelBinding`, and `EmbodimentBinding`. Inbound routing resolves trusted destination and sender identity before Timeline admission; infrastructure presence does not redefine Person or Relationship.

## Decision 11.B — Modality acquisition and presentation truth

Rich modality separates received capture, derived representation, semantic interaction/output, rendering, presentation, and stronger reception evidence:

```text
received media ≠ transcript
transcript ≠ admitted proposition
adopted ≠ rendered ≠ presented
presented ≠ read/heard ≠ understood
```

Streaming presentation records exact presented extent; social interruption does not automatically resume unpresented remainder.

## Decision 12.A — PresentationProfile, AffectState, InteractionPolicy

`PresentationProfile` is durable versioned presentation configuration outside Self. `AffectState` is bounded source-linked current interactional/appraisal state, not stable personality. `InteractionPolicy` is an immutable derived control snapshot. Style may shape truthful expression but cannot alter epistemic truth or authority.

## Decision 13.A — ConversationOpenLoop

`ConversationOpenLoop` is durable relationship-scoped unresolved conversational dependency. It is not MemoryClaim, DelegatedTask, Commitment, Trigger, or WorkRun. Lifecycle distinguishes resolved, cancelled, superseded, and expired; unfinished dialogue does not authorize background work or proactive contact.

The executable F4 slice now implements one bounded `DECISION` open-loop kind. Opening and explicit `RESOLVED`/`CANCELLED` closure are append-oriented. Resume selects exactly one unresolved matching loop by relationship, records that loop explicitly in `ContextProjection`, and fails closed on missing or ambiguous state rather than using latest-wins or model-selected history.

## Decision 14.A — Whole-system hydration and recovery

Recovery is deterministic reconstruction from Alsoul-owned durable state, not provider/model runtime restoration. Readiness is operation-specific. Canonical identity/Self and required Relationship integrity are hard blockers; other missing domains degrade/block only dependent operations. Recovery resumes from the furthest trustworthy durable stage.

## Decision 15.A — F4 physical persistence

F4 uses a transactional relational store. Self and Relationship use immutable complete revisions plus current heads. Timeline, evidence, claims, captures, WorldResults, ContextProjections, generated/adopted outputs, presented history, and the bounded ConversationOpenLoop lifecycle are immutable or append-oriented. External calls occur outside long-lived database transactions.

## Decision 15.B — F4 application services and recovery state

Canonical F4 state advances only through typed semantic application services. Database-command retries use stable operation identity and request digests. New external acquisition creates a new Observation; new model execution creates a new ModelInvocation; output adoption and presentation have separate idempotency fences. Response recovery stage is derived from canonical rows rather than stored as a mutable turn-status authority. Open-loop-aware projection reuse additionally rechecks that its selected loop remains the sole active matching loop before another provider execution.

See:

- [Architecture Checkpoint — Decisions 11.A through 15.B](ARCHITECTURE_CHECKPOINT_11_15.md)
- [ADR-005](adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006](adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)
- [F4 Implementation Bootstrap](F4_IMPLEMENTATION_BOOTSTRAP.md)
- [F4 Conversation Open Loop](F4_CONVERSATION_OPEN_LOOP.md)

## Current implementation boundary

The executable walking skeleton now includes persistent identity/relationship, canonical first-party text history, one evidence-grounded personal memory, fresh world acquisition/result, bounded source-free conversation, mechanically selected immediate-prior Timeline context, one relationship-scoped `DECISION` ConversationOpenLoop, immutable ContextProjection, model invocation, output adoption, presentation, and complete runtime reconstruction. Broader open-loop kinds, automatic expiry/supersession, generic semantic history retrieval, effectful work, durable tasks, proactivity, rich modality, and affect remain outside F4 implementation.
