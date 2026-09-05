# Alsoul Foundation Decision Ledger

**Status:** Convergence ledger; pre-ADR  
**Publication:** GitHub-safe

This ledger records the foundation decisions currently treated as converged enough to constrain implementation. It is intentionally concise. Individual ADRs may later replace ledger entries as implementation begins.

## Decision 01 — Canonical Self identity boundary

`SelfModel` is canonical continuity-bearing state distinct from `CompanionPerson` identity.

```text
CompanionPerson
≠ SelfModel
≠ Presentation Profile
≠ RelationshipState
```

Provider/model configuration does not define the person.

## Decision 02.A — Constitutional Self

Foundation constitutional Self contains only:

```text
role = PERSONAL_COMPANION
```

Architecture policy, authority, relationship state, autobiography, presentation, memory, and user modeling do not belong in constitutional Self.

## Decision 02.B — Slowly Mutable Self

Foundation slowly mutable Self contains only:

```text
preferred_name = "Alsoul"
```

No generic personality scalar/profile is canonical Self state.

## Decision 02.C — Narrative Self

Narrative Self is a rebuildable interpretation of the companion, not canonical `SelfModel` and not autobiographical evidence.

It is not required for the first vertical slice.

## Decision 02.D — Self revision and hydration

Canonical Self uses immutable complete revisions selected by a stable current head.

Stale writes are fenced by expected revision. Missing or invalid canonical Self fails closed for cognition as that person.

## Decision 03.A — RelationshipState

`RelationshipState` is the canonical durable relationship edge between one `CompanionPerson` and one durable counterpart.

Foundation shape:

```text
RelationshipState {
    relationship_id
    relationship_revision
    companion_person_id
    counterpart_id
}
```

Thread, surface, channel, provider, and credential identity do not define the relationship.

## Decision 03.B — RelationshipExperience

`RelationshipExperience` is a derived evidence-grounded interpretation of patterns within a relationship.

It is distinct from PersonModel, RelationshipState, AffectState, authority, and interaction policy.

It is not required for the first vertical slice.

## Decision 03.C — Relationship revision and recovery

Canonical RelationshipState uses immutable complete revisions selected by a current head.

Recovery resolves an existing relationship. It does not use an implicit get-or-create path that could fabricate continuity after state loss.

## Decision 04.A — CounterpartPerson

`CounterpartPerson` is the durable Alsoul-side identity anchor for the external counterpart.

Foundation shape:

```text
CounterpartPerson {
    counterpart_id
}
```

Names, profile facts, accounts, credentials, and authority are separate state.

External infrastructure identity resolves through explicit bindings rather than model inference.

## Decision 04.B — PersonClaim

A `PersonClaim` is an admitted durable evidence-grounded proposition held by one `CompanionPerson` about one `CounterpartPerson`.

Foundation PersonClaims are factual only.

Evidence linkage is first-class and many-to-many.

## Decision 04.C — PersonModel

`PersonModel` is a rebuildable current projection over admissible PersonClaims:

```text
PersonModel(P1 → U1)
```

It is not an authoritative user-profile blob and need not be separately persisted in the first vertical slice.

## Decision 04.D — PersonClaim admission and projection

Claims are admitted through a governed boundary from recoverable evidence.

Claim proposition content is immutable after admission.

Correction/currentness is represented through explicit claim relations rather than mutable `is_current` fields or latest-timestamp selection.

No global per-subject claim revision is required for the first vertical slice.

## Decision 05.A — EvidenceItem

`EvidenceItem` is an immutable durable evidentiary anchor over specific recoverable source material.

Evidence origin, claim derivation, and user-facing epistemic presentation are separate dimensions.

Generated companion output can establish what the companion generated, but does not independently establish the truth of its generated content.

## Decision 05.B — InteractionEvent and canonical Timeline

The canonical Timeline is append-oriented durable shared interaction history scoped to a relationship.

Foundation event kinds:

```text
COUNTERPART_INPUT
COMPANION_PRESENTED_OUTPUT
```

Model generation is not shared history until the presentation boundary is crossed.

Canonical ordering uses a relationship-local monotonic `timeline_seq`; timestamps retain their own occurrence/recording semantics.

## Decision 05.C — MemoryClaim

A `MemoryClaim` is an admitted durable evidence-grounded proposition carried forward for future recall within an explicit memory scope.

Historical retention does not imply memory admission.

For the first vertical slice, a factual person-scoped claim may physically satisfy both `MemoryClaim` and `PersonClaim` semantics.

## Decision 05.D — Memory lifecycle

Memory admission, eligibility, retrieval, and context projection are separate stages.

Scope/currentness/support precede relevance ranking.

A future `FORGET` operation is a durable recall/re-admission fence, not factual contradiction and not ordinary historical deletion.

No global MemoryHead or memory revision is required.

## Decision 06.A — Investigation, Observation, WorldResult

`Investigation` is the inquiry container.

`Observation` records that actual world-facing acquisition occurred.

`WorldResult` is an immutable evidence-backed conclusion derived within the Investigation.

Search intent, tool invocation, and model prior knowledge are not observations.

## Decision 06.B — WorldSourceCapture

A successful world Observation produces an immutable durable `WorldSourceCapture` representing the material actually acquired.

Evidence points to the capture, not a mutable live location.

Search discovery and underlying-source fetch are separate observations when both occur.

External captures retain a content digest for integrity while capture identity remains acquisition-specific.

## Decision 06.C — WorldResult derivation and freshness

A WorldResult becomes admitted only after evidence materially supports both the proposition and the Investigation objective.

Freshness is use-relative rather than a universal stored score.

For the first vertical slice, a freshness-sensitive current question always performs a new Investigation during the current turn.

Unresolved material contradiction blocks use as settled checked truth.

## Next convergence boundary — Decision 07.A

`ContextProjection` remains the next unresolved foundation boundary.

It must define:

```text
what canonical/derived state may enter cognition
which source revisions/frontiers are recorded
how relevant state may be summarized or omitted
how epistemic provenance survives rendering
how a model invocation is bound to the exact canonical state it saw
how provider-specific prompt material remains a projection rather than authority
```
