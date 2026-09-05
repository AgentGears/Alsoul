# Alsoul Architecture Convergence

**Status:** Pre-implementation foundation  
**Publication:** GitHub-safe

This document records the current normalized architecture boundaries that implementation must preserve. It is intentionally narrower than a complete product architecture.

## 1. Authority direction

Canonical state flows toward cognition through rebuildable projections.

```text
canonical identity/history/evidence
        ↓
admitted durable claims/results
        ↓
derived current models
        ↓
ContextProjection
        ↓
model/provider context
        ↓
generated output
        ↓
presentation/effect boundaries
```

Authority must not flow backward merely because a model generated plausible text.

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

For the first vertical slice, the required origin classes are:

```text
COUNTERPART_STATEMENT
SEARCH_RESULT
```

Evidence attachment never substitutes for semantic support.

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

For the foundation slice, evidence that qualifies a WorldResult as a current checked result must trace through its `EvidenceItem` and `WorldSourceCapture` to an `Observation` with the same `investigation_id` as the WorldResult. Evidence acquired by an older or different Investigation cannot be relabeled as acquisition performed for the current Investigation.

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

## 9. ContextProjection boundary

Canonical state must enter model cognition through an explicit rebuildable projection.

The projection must preserve enough source lineage to distinguish at least:

```text
remembered counterpart statement
current checked world result
historical checked result
direct observation
unverified inference
```

Model-facing prose is a rendering of this projection, not a source of canonical truth.

The exact `ContextProjection` contract is the next convergence boundary.

## 10. Foundation persistence patterns

Different domains use different persistence semantics deliberately.

```text
SelfModel
    immutable complete revisions + current head

RelationshipState
    immutable complete revisions + current head

Timeline
    append-only immutable events + relationship-local sequence

EvidenceItem
    immutable evidence anchors

MemoryClaim / PersonClaim
    immutable admitted propositions + relations

Observation / WorldSourceCapture / WorldResult
    immutable historical acquisition/result records

PersonModel
    rebuildable derived view

ContextProjection
    rebuildable turn-specific view
```

No single universal event-sourcing or mutable-document pattern is imposed across domains where the semantics differ.
