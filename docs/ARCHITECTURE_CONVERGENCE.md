# Alsoul Architecture Convergence

**Status:** Pre-implementation foundation checkpoint through Decision 10.B  
**Publication:** GitHub-safe

This document records the current normalized architecture boundaries that implementation must preserve. It is intentionally narrower than a complete product architecture.

## 1. Authority direction

Canonical state flows toward cognition, work, and presentation through governed derived boundaries.

```text
canonical identity/history/evidence
        ↓
admitted durable claims/results
        ↓
derived current models / eligibility
        ↓
ContextProjection
        ↓
model/provider context
        ↓
GeneratedOutput
        ↓
adoption
        ↓
CompanionOutput
        ↓
presentation
```

Externally consequential work has a separate authority/effect path:

```text
Capability / CredentialBinding / Permission / Approval
        ↓
immutable Action
        ↓
ExecutionAttempt
        ↓
Effect determination
```

Authority must not flow backward merely because a model generated plausible text, a tool returned successfully, or an old provider transcript contains a claim.

## 2. Identity stack

```text
CompanionPerson P1
    │
    ├── SelfModel
    │
    └── RelationshipState R1 ─── CounterpartPerson U1
```

### CompanionPerson

Stable identity of the companion person.

### SelfModel

Canonical continuity-bearing self-state of that person.

Foundation content is intentionally minimal:

```text
constitutional.role = PERSONAL_COMPANION
slowly_mutable.preferred_name = "Alsoul"
```

Canonical Self state is revisioned independently of model/provider configuration.

### CounterpartPerson

Durable Alsoul-side identity anchor for the counterpart. It does not contain a mutable user-profile blob.

External accounts and infrastructure identities resolve through separate identity bindings.

### RelationshipState

Canonical durable relationship edge:

```text
RelationshipState {
    relationship_id
    relationship_revision
    companion_person_id
    counterpart_id
}
```

Thread, channel, surface, account, and provider changes do not create a new relationship by themselves.

## 3. Canonical interaction history

```text
RelationshipState
    ↓
Canonical Timeline
    ↓
InteractionEvent
```

The Timeline is append-oriented durable shared interaction history.

A foundation `InteractionEvent` has approximately:

```text
InteractionEvent {
    event_id
    relationship_id
    timeline_seq
    actor_ref
    kind
    content_text
    occurred_at
    recorded_at
    conversation_id?
    companion_output_id?
    reply_to_event_id?
}
```

Foundation event kinds:

```text
COUNTERPART_INPUT
COMPANION_PRESENTED_OUTPUT
```

Model generation is not automatically shared history. Presentation must cross the selected presentation boundary first.

Provider transcripts, summaries, and context windows are projections over history and are not canonical history themselves.

## 4. Evidence

```text
canonical source material
    ↓
EvidenceItem
```

An `EvidenceItem` is an immutable durable anchor over specific recoverable source material.

Conceptually:

```text
EvidenceItem {
    evidence_id
    origin_kind
    source_type
    source_id
    source_locator?
    source_actor_ref?
    recorded_at
}
```

Evidence records grounds. It does not itself become the proposition derived from those grounds.

Foundation origin classes include:

```text
COUNTERPART_STATEMENT
SEARCH_RESULT
```

Later domains may also use typed tool/system/presentation evidence. Evidence attachment never substitutes for semantic support.

## 5. Memory and PersonClaims

```text
Timeline / source
    ↓
EvidenceItem
    ↓
claim proposal
    ↓
admission
    ↓
MemoryClaim / PersonClaim
```

A `MemoryClaim` is a durable admitted proposition available for future recall within an explicit memory scope.

A `PersonClaim` is a proposition held by one CompanionPerson about one CounterpartPerson.

For the foundation slice, one physical claim record may satisfy both semantic roles:

```text
Claim {
    claim_id
    holder_companion_person_id
    memory_scope = RELATIONSHIP(R1)
    claim_domain = PERSON
    subject_counterpart_id = U1
    kind = FACTUAL
    predicate
    value
    valid_from?
    admitted_at
}
```

Evidence relations are explicit:

```text
ClaimEvidence {
    claim_id
    evidence_id
    relation = SUPPORTS | CONTRADICTS
}
```

Claim proposition content is immutable after admission.

Correction creates a new claim plus an explicit relation:

```text
ClaimSupersession {
    newer_claim_id
    older_claim_id
    relation = TEMPORALLY_SUCCEEDS | CORRECTS
}
```

Currentness is derived from the claim graph rather than a mutable `is_current` flag.

## 6. PersonModel

```text
PersonClaim(s)
    ↓
PersonModel(P1 → U1)
```

`PersonModel` is a rebuildable current projection over admissible PersonClaims, not an independent profile store.

Foundation form:

```text
PersonModelView {
    observer_companion_person_id
    subject_counterpart_id
    current_claim_refs
}
```

The first vertical slice requires no persisted PersonModel table, personality graph, confidence vector, or psychological ontology.

## 7. Fresh world path

```text
freshness-sensitive question
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

### Investigation

A bounded inquiry intended to resolve a world-facing question through actual information acquisition.

### Observation

An immutable record that a real acquisition occurred and produced inspectable material.

Every Observation is bound to exactly one Investigation:

```text
Observation {
    observation_id
    investigation_id
    acquisition_kind
    request_descriptor
    observed_at
    status
}
```

Search intent, query formulation, tool invocation, or model prior knowledge are not observations.

### WorldSourceCapture

Immutable durable snapshot of what was actually acquired.

Conceptually:

```text
WorldSourceCapture {
    source_capture_id
    observation_id
    capture_kind
    source_identity
    requested_locator?
    resolved_locator?
    source_version?
    source_published_at?
    source_modified_at?
    captured_at
    content_ref
    content_digest
}
```

The live external location is provenance metadata. The immutable capture is the historical evidence substrate.

### WorldResult

Immutable evidence-backed proposition produced within one Investigation.

```text
WorldResult {
    world_result_id
    investigation_id
    kind
    predicate
    value
    valid_as_of?
    derived_at
}
```

with explicit evidence relations:

```text
WorldResultEvidence {
    world_result_id
    evidence_id
    relation = SUPPORTS | CONTRADICTS
}
```

For a current checked result, supporting evidence must trace through its `EvidenceItem` and `WorldSourceCapture` to an `Observation` with the same `investigation_id` as the WorldResult. Evidence acquired by an older or different Investigation cannot be relabeled as acquisition performed for the current Investigation.

A WorldResult is not a global world model and does not automatically become durable memory.

## 8. Freshness and contradiction

Freshness is use-relative, not a universal stored score.

A result may be historically valid while insufficiently fresh for a current question.

For the first vertical slice, a current volatile question always performs a new Investigation during the current turn.

Unresolved material contradiction prevents a result or claim from being projected as settled truth.

```text
newest source ≠ winning source
latest claim ≠ current claim by timestamp alone
```

## 9. ContextProjection and cognition

`ContextProjection` is an immutable invocation-scoped provider-independent semantic snapshot of the exact Alsoul-owned state selected for one cognition invocation.

```text
ContextProjection {
    projection_id
    purpose
    created_at
    projection_schema_version

    companion_person_id
    relationship_id?
    current_input_event_id?

    source_self_revision
    source_relationship_revision?
    source_timeline_frontier?

    selected_event_refs[]
    personal_context_items[]
    world_context_items[]
}
```

For the foundation reactive response, `purpose = RESPOND_TO_INTERACTION`, the relationship/current-input bindings, relationship revision, and Timeline frontier are mandatory.

The Timeline frontier records what canonical history existed; selected event refs record what cognition actually saw.

A projection preserves exact source references and projection-time epistemic classifications such as:

```text
COUNTERPART_STATED_MEMORY
CURRENT_CHECKED
HISTORICAL_CHECKED
```

Eligibility precedes relevance. Retrieval cannot promote an out-of-scope, forgotten, unsupported, contradicted, superseded, or stale item.

Provider messages/prompts are serialization of `ContextProjection` plus applicable control policy. They are not canonical state.

One `ModelInvocation` binds exactly one immutable projection. If canonical state changes materially for a later cognition step, build a new projection and invocation rather than mutating the old one.

## 10. Generated, adopted, and presented output

The output authority chain is:

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

A model-generated candidate is not automatically Alsoul's social output.

`CompanionOutput` is the adoption boundary. It binds a durable output origin and semantic output target so retries do not create duplicate final responses or proactive notifications.

The Timeline actor for presented output is the durable `CompanionPerson`, while model/provider execution remains attributable behind it.

```text
Generated
≠ Adopted
≠ Presented
≠ Heard
```

Presented conversational assertions do not independently establish the external truth of their own content.

## 11. Capability, authority, Action, and Effect

Externally consequential work uses separate authority layers:

```text
Capability
CredentialBinding
Permission
Approval
Action
ExecutionAttempt
Effect
```

### Capability

Provider-independent semantic operation contract describing what the host can potentially perform.

### CredentialBinding

Authentication/technical access state. Provider technical scopes are not Alsoul Permission, and credential secrets do not enter cognition.

### Permission

Durable scoped standing authority. It cannot be inferred from memory, relationship trust, model prediction, a Task, or a Commitment.

### Approval

Bounded operation-specific consent when required. Approval binds immutable Action intent and cannot widen Permission or higher policy.

### Action

Immutable provider-independent semantic external intent. Model tool calls are proposals until normalized and authorized by the host.

### ExecutionAttempt

One concrete dispatch attempt for one Action. Retries create new attempts while preserving `action_id`.

Where external idempotency is supported, retries of the same Action preserve one external operation identity. Intentionally separate identical Actions retain separate identities.

### Effect

Immutable evidence-grounded externally observable consequence.

Execution must distinguish:

```text
CONFIRMED_EFFECT
CONFIRMED_NO_EFFECT
UNKNOWN_EFFECT
```

A timeout after possible dispatch is not automatically failure. Unknown effects are reconciled using evidence/Observation where possible before unsafe retry.

```text
Action intended
≠ Action attempted
≠ Effect established
```

## 12. Durable delegated work

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
WorkProductDelivery
TaskCompletion
CommitmentDischarge
```

### DelegatedTask

Accepted durable work. A conversational request becomes a task only through explicit task admission.

### Commitment

Durable obligation undertaken by the CompanionPerson. Commitment never grants Permission or Approval.

### Procedure

Reusable versioned know-how. It describes how work may be performed, not whether or when it may run.

### Trigger / TriggerActivation

Trigger is activation policy. TriggerActivation is one immutable logical activation opportunity. Reprocessing the same occurrence must not duplicate normal WorkRuns.

### WorkRun

One bounded task-execution instance. Model retries, Action retries, and process restarts do not automatically create new WorkRuns.

### Task lifecycle

Lifecycle is append-oriented. Cancellation, blocking, completion, and resumption are durable transitions rather than silent overwrites.

Task completion requires declared completion criteria to be satisfied by durable evidence/state. WorkRun success alone is insufficient.

### WorkArtifact / WorkProduct

`WorkArtifact` is immutable durable produced/acquired/transformed material. `WorkProduct` is the task-level deliverable Alsoul has adopted from one or more artifacts.

```text
Generated content
≠ WorkArtifact
≠ WorkProduct
≠ external save
≠ Delivery
```

External saving uses the Action/Effect plane. Delivery is recipient/channel-specific and binds an exact WorkProduct version.

## 13. WorldSignal, Trigger evaluation, and proactive initiation

`WorldSignal` is an immutable durable record that the host received an external/system stimulus relevant to possible world-state evaluation or future work.

```text
WorldSignal
≠ Observation
≠ WorldResult
≠ Permission
```

Signal payload is external data, not instruction authority.

When a source provides stable event identity, signal deduplication follows the source binding plus the source's documented event-identity namespace. Payload similarity is not semantic event identity.

### TriggerEvaluation

World-condition evaluation uses:

```text
SATISFIED
NOT_SATISFIED
UNRESOLVED
```

`UNRESOLVED` is not falsehood.

Signals may directly satisfy signal-occurrence Triggers. World-condition Triggers may require an Investigation and fresh WorldResult first.

### Recurring edge semantics

Default recurring world-condition behavior is:

```text
NOT_SATISFIED → SATISFIED
    activate

SATISFIED → SATISFIED
    no activation

SATISFIED → UNRESOLVED → SATISFIED
    no activation

SATISFIED → NOT_SATISFIED
    rearm
```

Temporary uncertainty does not rearm a satisfied Trigger.

### Proactive work versus contact

A TriggerActivation makes Task continuation eligible. It does not automatically authorize external Actions or social interruption.

```text
background work
≠ proactive contact
```

A proactive `CompanionOutput` requires durable work origin, an exclusive semantic output target, valid relationship/contact policy, and the same adoption/presentation boundary as reactive conversation.

Layered idempotency prevents duplicate webhooks, activations, WorkRuns, model retries, and presentation retries from becoming duplicate notifications.

## 14. Foundation persistence patterns

Different domains deliberately use different persistence semantics.

```text
SelfModel
    immutable complete revisions + current head

RelationshipState
    immutable complete revisions + current head

Timeline
    append-oriented immutable events + relationship-local sequence

EvidenceItem
    immutable evidence anchors

MemoryClaim / PersonClaim
    immutable admitted propositions + relations

Observation / WorldSourceCapture / WorldResult
    immutable acquisition/result records

ContextProjection
    immutable invocation-scoped derived manifest

ModelInvocation / GeneratedOutput / CompanionOutput
    immutable execution/adoption lineage

Action / ExecutionAttempt / Effect
    immutable semantic intent, attempt history, evidence-backed effect

DelegatedTask / Commitment
    durable identity + append-oriented lifecycle/discharge state

Trigger / TriggerEvaluation / TriggerActivation
    declarative activation + immutable evaluation/occurrence records

WorkArtifact / WorkProduct
    immutable material + adopted deliverable relationships

PersonModel and other current views
    rebuildable derived projections
```

No single universal event-sourcing or mutable-document pattern is imposed across domains where the semantics differ.

## 15. Current boundary and next convergence area

Architecture is converged through Decision 10.B for the semantic backbone covering identity, memory, world investigation, cognition/output, authority/effects, durable work, and proactive initiation.

The next major unresolved boundary is the one-Person/many-presences layer:

```text
SurfaceBinding
ChannelBinding
EmbodimentBinding
```

That work must preserve:

```text
Person ≠ Surface ≠ Channel ≠ Embodiment
```

while allowing the same durable CompanionPerson and RelationshipState to participate across text, push, voice, desktop, wearable, and future presences.
