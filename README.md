# Alsoul

> **A companion with a world, not a chatbot with tools.**

Alsoul is a persistent personal companion architecture designed to remain one continuous person across model, process, thread, surface, channel, and provider changes.

The project has entered **foundation implementation**. The semantic backbone is converged through identity, history, memory, fresh world access, cognition/output, authority/effects, durable delegated work, proactivity, presence/modality, presentation policy, conversational open loops, recovery, and the F4 persistence/service boundary. The first executable walking skeleton is intentionally much narrower than the full architecture.

## Product thesis

Alsoul should feel like someone who knows you, lives in your world, and knows the limits of what they know and can do.

Its internal architecture may be sophisticated. The user's mental model should remain simple:

```text
                    Alsoul
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   knows me       has a world      can help me
       │              │              │
   remembers        can check      can act
   understands      can notice     can work
   our history      can observe    can follow up
```

The primary trust quality is **felt honesty**. When Alsoul says it remembers, checked, observed, inferred, acted, scheduled, produced, delivered, or is uncertain, those words should correspond to real internal state.

## Foundation principles

```text
Companion ≠ Model
Self ≠ Relationship ≠ World
Memory ≠ Observation
Historical Evidence ≠ Derived Memory
Observation ≠ Interpretation
Fact about a person ≠ PersonModel claim ≠ Interaction Policy
Search result ≠ Companion belief
Person ≠ Thread ≠ Surface ≠ Channel ≠ Embodiment
Identity ≠ Credential ≠ Authority
Capability availability ≠ permission ≠ approval ≠ effect
Failed effect ≠ uncertain effect
Context reset ≠ historical deletion
Memory proposal ≠ memory admission
Generated output ≠ adopted output ≠ presented output ≠ heard output
Authoritative result ≠ context projection
Procedure ≠ Trigger ≠ WorkRun
Task ≠ Commitment
WorkRun ≠ Action
Action ≠ ExecutionAttempt ≠ Effect
WorkArtifact ≠ WorkProduct ≠ Delivery
WorldSignal ≠ Observation
background work ≠ proactive contact
PresentationProfile ≠ SelfModel
AffectState ≠ stable personality
ConversationOpenLoop ≠ DelegatedTask ≠ Commitment
persistence ≠ recoverability ≠ hydration
```

## Current architecture map

```text
CompanionPerson
    │
    ├── SelfModel
    ├── PresentationProfile
    ├── SurfaceBinding / ChannelBinding / EmbodimentBinding
    │
    └── RelationshipState ─── CounterpartPerson
            │                     │
            │                     └── PersonClaim / PersonModel
            │
            └── Canonical Timeline
                    │
                    └── EvidenceItem
                            │
                            └── MemoryClaim / PersonClaim

Fresh world question
    │
    └── Investigation
            │
            └── Observation
                    │
                    └── WorldSourceCapture
                            │
                            └── EvidenceItem
                                    │
                                    └── WorldResult

Memory / PersonModel / WorldResult / current interaction
    │
    └── InteractionPolicy
            │
            └── ContextProjection
                    │
                    └── ModelInvocation
                            │
                            └── GeneratedOutput
                                    │
                                    └── CompanionOutput
                                            │
                                            └── presented Timeline event

Effectful work
    │
    ├── Capability / CredentialBinding
    ├── Permission / Approval
    └── Action
            │
            └── ExecutionAttempt
                    │
                    └── Effect

Durable work
    │
    └── DelegatedTask
            ├── Commitment
            ├── Trigger → TriggerActivation
            ├── Skill / Procedure
            └── WorkRun
                    ├── Investigation / Action
                    └── WorkArtifact → WorkProduct → Delivery

Proactive world path
    │
    └── WorldSignal
            │
            └── TriggerEvaluation
                    │
                    └── TriggerActivation
                            │
                            └── WorkRun
                                    │
                                    └── bounded proactive output
```

## Foundation walking skeleton

The first executable vertical slice remains intentionally much smaller than the full architecture. It proves one continuous companion that can:

1. recover the same durable person and relationship after complete process death;
2. recover one evidence-grounded personal memory;
3. receive a question requiring current external information;
4. perform a fresh investigation and preserve what was actually acquired;
5. derive an evidence-backed world result;
6. build an immutable ContextProjection carrying exact personal/world provenance;
7. bind one model invocation to that projection;
8. distinguish generated candidate output from Alsoul-adopted output and actual shared-history presentation; and
9. present memory, checked information, and interpretation as distinct epistemic classes.

The target interaction is mechanically capable of meaning:

```text
"You told me ..."
"I checked ..."
"My take is ..."
```

without those distinctions being prompt conventions or stylistic guesses.

The implementation bootstrap uses deterministic world/model adapters in the acceptance suite and a file-backed relational store to exercise complete runtime reconstruction. Effectful external Actions, background delegated work, proactive monitoring, multi-channel delivery, and rich modality remain outside F4.

## Implementation

The first source tree lives under `src/alsoul` and is organized around semantic boundaries rather than provider APIs:

```text
src/alsoul/
    domain/
    storage/
    services/
    adapters/
```

Database migrations live under `migrations/`, and executable architecture tests live under `tests/`.

Foundation identity creation is an explicit administration boundary through `FoundationBootstrapper`; ordinary `FoundationServices` fail closed rather than recreating missing Person/Relationship roots. Provider-independent adapter contracts now sit above deterministic acceptance adapters and a generic HTTP world-acquisition adapter, while semantic Observation/Evidence/WorldResult admission remains inside the application-service boundary.

The repository continuously verifies source/test compilation, the executable acceptance suite, and migration upgrade/downgrade.

See [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md) for the concrete walking-skeleton scope and [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md) for the post-bootstrap trust-boundary hardening.

## Documentation

Core documents:

- [Product Constitution](docs/PRODUCT_CONSTITUTION.md)
- [Architecture Convergence](docs/ARCHITECTURE_CONVERGENCE.md)
- [Foundation Walking Skeleton](docs/FOUNDATION_WALKING_SKELETON.md)
- [Decision Ledger](docs/DECISION_LEDGER.md)
- [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md)
- [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md)
- [Architecture Checkpoint — Decisions 11.A through 15.B](docs/ARCHITECTURE_CHECKPOINT_11_15.md)

Architecture decision records:

- [ADR-001 — Context and Output Boundary](docs/adr/ADR-001_CONTEXT_AND_OUTPUT.md)
- [ADR-002 — Authority, Action, Execution, and Effect](docs/adr/ADR-002_AUTHORITY_AND_EFFECTS.md)
- [ADR-003 — Durable Work, Commitments, Tasks, and Deliverables](docs/adr/ADR-003_DURABLE_WORK.md)
- [ADR-004 — World Signals, Triggers, and Proactive Initiation](docs/adr/ADR-004_PROACTIVITY.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](docs/adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](docs/adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)

## Status

Foundation implementation hardening. The current code exercises the F4 persistence/service boundary, derives recovery progress from canonical rows, separates explicit identity bootstrap from runtime services, and continuously verifies the executable foundation contract. Broader F2 domains remain architecturally specified but are deliberately not implemented in the walking skeleton yet.
