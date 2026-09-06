# Alsoul Architecture Convergence

**Status:** Foundation implementation checkpoint through Decision 15.B  
**Publication:** GitHub-safe

This document records the normalized architecture boundaries that constrain the current Alsoul foundation implementation. Detailed rationale lives in the Decision Ledger and ADRs.

## 1. Authority direction

Canonical Alsoul-owned state flows toward cognition, work, and presentation through governed boundaries:

```text
canonical identity / history / evidence
        ↓
admitted claims / world results
        ↓
derived current views / eligibility
        ↓
InteractionPolicy + ContextProjection
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
```

Externally consequential work uses a separate authority/effect chain:

```text
Capability / CredentialBinding / Permission / Approval
        ↓
Action
        ↓
ExecutionAttempt
        ↓
Effect determination
```

Authority never flows backward merely because a model generated plausible text, a provider returned success, or an old transcript contains a claim.

## 2. Identity and relationship

```text
CompanionPerson P1
    │
    ├── SelfModel
    │
    └── RelationshipState R1 ─── CounterpartPerson U1
```

`CompanionPerson` is the durable identity of Alsoul. `SelfModel` is canonical continuity-bearing first-person state. Foundation Self remains deliberately small:

```text
constitutional.role = PERSONAL_COMPANION
slowly_mutable.preferred_name = "Alsoul"
```

Canonical Self and Relationship state use immutable complete revisions selected by stable current heads. Recovery never silently recreates missing identity state.

`CounterpartPerson` is the durable Alsoul-side identity anchor for the counterpart. External identities resolve through explicit bindings, not model inference.

## 3. Presence is not Person

One `CompanionPerson` may appear through many presences:

```text
CompanionPerson
≠ SurfaceBinding
≠ ChannelBinding
≠ EmbodimentBinding
```

Inbound routing resolves trusted destination binding → CompanionPerson and trusted sender identity → CounterpartPerson before a canonical interaction event is admitted. Thread, surface, channel, embodiment, provider, and credential changes do not redefine the Person or Relationship.

Rich modality preserves stronger distinctions:

```text
received media ≠ transcript
transcript ≠ admitted proposition
adopted ≠ rendered ≠ presented
presented ≠ read/heard ≠ understood
```

## 4. Canonical Timeline and evidence

The canonical Timeline is append-oriented shared relationship history:

```text
RelationshipState
    ↓
InteractionEvent
```

Foundation event kinds are:

```text
COUNTERPART_INPUT
COMPANION_PRESENTED_OUTPUT
```

Model generation is not shared history. A generated candidate becomes shared history only after adoption and the selected presentation boundary.

`EvidenceItem` is an immutable durable anchor over specific recoverable source material. Evidence records grounds; it is not itself the proposition derived from those grounds.

## 5. Memory and person understanding

```text
Timeline / source
    ↓
EvidenceItem
    ↓
claim proposal
    ↓
admission
    ↓
PersonClaim / MemoryClaim
```

Claims are immutable admitted propositions. Evidence linkage is explicit. Correction creates a new claim plus explicit supersession/correction relations; there is no mutable `is_current` authority flag and no latest-timestamp-wins rule.

`PersonModel` is a rebuildable current projection over admissible PersonClaims. It is not a mutable user-profile blob.

Foundation F4 uses one physical factual relationship-scoped claim to satisfy both PersonClaim and MemoryClaim semantics for the walking-skeleton predicate:

```text
primary_machine.memory_gb
```

## 6. Fresh world acquisition

A current world-facing answer follows:

```text
fresh question
    ↓
Investigation
    ↓
Observation
    ↓
WorldSourceCapture
    ↓
EvidenceItem
    ↓
WorldResult
```

An `Observation` belongs to exactly one `Investigation`. A `WorldSourceCapture` is the immutable material actually acquired; a mutable live URL is only provenance metadata. A `WorldResult` is an immutable evidence-backed proposition derived within one Investigation.

For a result to be projected as `CURRENT_CHECKED` in F4:

```text
WorldResult
→ EvidenceItem
→ WorldSourceCapture
→ Observation
→ same Investigation
```

must validate, the acquisition must be temporally appropriate for the current question, and explicit stale `valid_as_of` information cannot be relabeled current. Unresolved material contradiction blocks settled checked use.

Freshness is use-relative rather than a stored global score.

## 7. ContextProjection and cognition

`ContextProjection` is an immutable invocation-scoped provider-independent semantic snapshot of the exact Alsoul-owned state selected for one cognition invocation.

It pins:

```text
CompanionPerson
Self revision
Relationship revision
Timeline frontier
selected interaction events
selected claims + support
selected WorldResults + support
projection-time epistemic classifications
```

Provider prompt/messages are a rendering of `ContextProjection`, not canonical state. Rendering dereferences the pinned revisions/items rather than re-reading mutable current heads.

One `ModelInvocation` binds exactly one ContextProjection. Model/provider identity is execution attribution, not Person identity.

## 8. Generated, adopted, and presented output

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
COMPANION_PRESENTED_OUTPUT InteractionEvent
```

Permanent distinction:

```text
Generated ≠ Adopted ≠ Presented ≠ Heard
```

`CompanionOutput` is the durable adoption boundary. The F4 adoption contract verifies that user-visible text exactly matches the canonical rendering of its structured semantic payload, so valid provenance metadata cannot be attached to unrelated prose.

Semantic output targets fence adoption races; presentation of one CompanionOutput is idempotent.

## 9. Presentation configuration, affect, and interaction policy

```text
SelfModel
≠ PresentationProfile
≠ AffectState
≠ InteractionPolicy
```

`PresentationProfile` is durable versioned presentation configuration outside Self. `AffectState` is bounded source-linked current interactional/appraisal state rather than stable personality. `InteractionPolicy` is an immutable derived control snapshot for one cognition/output situation.

Style may shape truthful expression. It cannot alter memory, world evidence, authority, external effect, commitment, or presentation truth.

## 10. Authority, Action, and Effect

Technical capability, credentials, standing permission, operation-specific approval, semantic action intent, concrete execution, and confirmed effect are separate:

```text
Capability
≠ CredentialBinding
≠ Permission
≠ Approval
≠ Action
≠ ExecutionAttempt
≠ Effect
```

Execution distinguishes:

```text
CONFIRMED_EFFECT
CONFIRMED_NO_EFFECT
UNKNOWN_EFFECT
```

Unknown effect survives restart and blocks unsafe blind retry. Strong completion language is downstream of a confirmed effect, not a transport return.

## 11. Durable delegated work

Durable work separates:

```text
DelegatedTask
Commitment
Skill / Procedure
Trigger
TriggerActivation
WorkRun
WorkArtifact
WorkProduct
Delivery
TaskCompletion
CommitmentDischarge
```

A conversational request becomes durable work only through explicit task admission. Procedure describes how; Trigger describes when work becomes eligible. TriggerActivation is one logical occurrence. WorkRun is one bounded task execution. Process/model/action retries do not automatically create new WorkRuns.

Task completion requires declared criteria satisfied by durable evidence/state; Commitment discharge remains separate.

## 12. World signals and proactive initiation

`WorldSignal` records receipt of an external/system stimulus. It is not automatically an Observation, WorldResult, Trigger satisfaction, Permission, or instruction to act.

`TriggerEvaluation` distinguishes:

```text
SATISFIED
NOT_SATISFIED
UNRESOLVED
```

Recurring world-condition triggers are edge-sensitive; temporary uncertainty does not rearm an already satisfied condition. Proactive work and proactive contact remain separate. Activation does not itself grant Action authority or social-contact authority.

## 13. ConversationOpenLoop

`ConversationOpenLoop` is durable relationship-scoped unresolved conversational dependency:

```text
ConversationOpenLoop
≠ MemoryClaim
≠ DelegatedTask
≠ Commitment
≠ Trigger
```

Loop lifecycle is append-oriented and distinguishes resolved, cancelled, superseded, and expired. Unfinished conversation does not become background work or permission to initiate follow-up.

## 14. Recovery and hydration

Recovery is deterministic reconstruction from Alsoul-owned durable state, not restoration of provider/model runtime.

```text
persistence ≠ recoverability
recoverability ≠ hydration
provider session ≠ CompanionPerson
```

Operation-specific readiness barriers govern ingress admission, cognition, work continuation, effectful execution, and presentation. Canonical identity/Self and required Relationship integrity are hard blockers; optional domains degrade only the operations whose truth depends on them.

Recovery resumes from the furthest trustworthy durable stage rather than replaying a whole turn or asking a model what probably happened.

## 15. F4 physical persistence and services

The F4 walking skeleton uses a transactional relational store.

```text
SelfModel / RelationshipState
    immutable complete revisions + current heads

Timeline
    append-oriented immutable events + relationship-local sequence

Evidence / Claims / Captures / WorldResults
    immutable or append-oriented provenance graph

ContextProjection
    immutable invocation manifest

ModelInvocation / GeneratedOutput / CompanionOutput
    attributable execution and adoption lineage
```

External network/model calls occur outside long-lived database transactions. Each semantic admission boundary commits a small internally valid stage.

Canonical F4 state advances only through typed semantic application services. Generic repository mutation is not an application API. Database-command retries use stable operation identity; a new world acquisition is a new Observation; a new model attempt is a new ModelInvocation; output adoption and presentation have their own semantic idempotency fences.

The recovery coordinator derives response progress from canonical rows rather than storing an authoritative mutable turn status.

See:

- [Architecture Checkpoint — Decisions 11.A through 15.B](ARCHITECTURE_CHECKPOINT_11_15.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)
- [F4 Implementation Bootstrap](F4_IMPLEMENTATION_BOOTSTRAP.md)

## 16. Current implementation boundary

The executable F4 slice intentionally implements only:

```text
persistent Person / Self / Relationship
canonical first-party text Timeline
one factual evidence-grounded personal memory
fresh Investigation / Observation / Capture / WorldResult
immutable ContextProjection
ModelInvocation / GeneratedOutput
CompanionOutput adoption
first-party text presentation
complete runtime reconstruction
```

Effectful Actions, durable Tasks, proactive monitoring, rich modality, AffectState, PresentationProfile adaptation, and ConversationOpenLoop persistence remain outside the first executable slice even though their semantic boundaries are fixed.

The next work is implementation hardening and expansion from this executable foundation, not reopening the core identity/memory/world/output boundaries without new evidence.
