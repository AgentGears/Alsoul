# ADR-006 — F4 persistence and application-service boundary

**Status:** Accepted
**Publication:** GitHub-safe

## Context

The foundation semantic model is sufficiently converged to implement the walking skeleton. The implementation needs physical constraints and transaction boundaries that preserve identity, provenance, freshness, generation/adoption/presentation separation, and crash recovery without encoding every future F2 domain.

## Decision

F4 uses a transactional relational store. Identity-bearing Self and Relationship state use stable identities, immutable complete revisions, and current heads. Timeline, evidence, claims, source captures, WorldResults, ContextProjections, GeneratedOutputs, CompanionOutputs, and presented events are immutable or append-oriented.

External network/model calls occur outside database transactions. The workflow commits small semantic stages so process death can occur safely between them.

Canonical state advances only through typed semantic application services. Generic repository mutation is not an application API. Application-command retries use stable operation identity and canonical request digests; reusing one operation identity for different semantic input is rejected.

The critical atomic boundaries are:

```text
Claim + SUPPORTS relation
WorldSourceCapture + EvidenceItem + Observation success
WorldResult + evidence relations
ContextProjection + selected-item/support manifest
GeneratedOutput + ModelInvocation success
CompanionOutput + exclusive OutputTarget
presented InteractionEvent + Timeline sequence advance
```

A new external acquisition is a new Observation. A new model attempt is a new ModelInvocation. A presentation retry of the same CompanionOutput is the same intended social presentation and resolves to one canonical Timeline event.

## Consequences

The F4 acceptance suite can mechanically reconstruct:

```text
presented InteractionEvent
↓
CompanionOutput
↓
GeneratedOutput
↓
ModelInvocation
↓
ContextProjection
├── PersonClaim → EvidenceItem → counterpart InteractionEvent
└── WorldResult → EvidenceItem → WorldSourceCapture → Observation → Investigation
```

Currentness and freshness are derived rather than stored as `is_current` or `is_fresh` booleans. Provider transcript/context remains replaceable infrastructure rather than persistence authority.
