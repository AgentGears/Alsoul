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

The primary trust quality is **felt honesty**. When Alsoul says it remembers, checked, observed, inferred, acted, scheduled, produced, delivered, presented, or is uncertain, those words should correspond to real internal state.

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
Generated output ≠ adopted output ≠ presentation attempt ≠ presented output ≠ heard output
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
                                            └── presentation acceptance
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
8. distinguish generated candidate output from Alsoul-adopted output, first-party presentation acceptance, and actual shared-history presentation; and
9. present memory, checked information, and interpretation as distinct epistemic classes.

The target interaction is mechanically capable of meaning:

```text
"You told me ..."
"I checked ..."
"My take is ..."
```

without those distinctions being prompt conventions or stylistic guesses.

The implementation bootstrap uses deterministic adapters in the acceptance suite and a file-backed relational store to exercise complete runtime reconstruction. Effectful external Actions, background delegated work, proactive monitoring, multi-channel delivery, read/heard receipts, and rich modality remain outside F4.

## Implementation

The first source tree lives under `src/alsoul` and is organized around semantic boundaries rather than provider APIs:

```text
src/alsoul/
    domain/
    storage/
    services/
    adapters/
    host/
```

Database migrations live under `migrations/`, and executable architecture tests live under `tests/`.

Foundation identity creation is an explicit administration boundary through `FoundationBootstrapper`; ordinary `FoundationServices` fail closed rather than recreating missing Person/Relationship roots.

Trusted first-party ingress is explicit through `FirstPartyIngress`. An authenticated transport assertion resolves only pre-existing CounterpartIdentityBinding, RelationshipState, SurfaceBinding, and ChannelBinding state before it can become a canonical `COUNTERPART_INPUT`. The model never participates in identity resolution, unknown identity fails closed, and semantic transport-event replay collapses to one Timeline event.

Provider execution is routed through Alsoul-owned orchestration boundaries. `WorldAcquisitionRunner` persists an Observation before a replaceable acquisition adapter runs and stops at captured evidence; `ModelGenerationRunner` persists ModelInvocation before dispatch and stops at GeneratedOutput. Neither path can bypass WorldResult admission, CompanionOutput adoption, or presentation.

Provider recovery is explicit. `RecoveryCoordinator` derives `MODEL_ATTEMPT_UNRESOLVED` for orphaned in-progress generation, `ProviderRecoveryCoordinator` can conservatively reconcile a known process-lost attempt to `UNKNOWN`, and the semantic service boundary prevents blind retry, stale ContextProjection reuse, and regeneration when a durable GeneratedOutput already exists.

Reactive orchestration is composed through `FoundationResponseCoordinator`. It derives progress from canonical rows, reuses already-durable Investigation/Capture/WorldResult/ContextProjection/GeneratedOutput state, and resumes after process death from the furthest trustworthy semantic boundary without persisting a parallel turn-status aggregate.

First-party presentation is now an explicit acceptance boundary. The coordinator derives a restart-stable semantic presentation key from the adopted `CompanionOutput` and exact surface/channel route, sends the exact content and digest through a provider-independent presentation adapter, and commits `COMPANION_PRESENTED_OUTPUT` only after validating a positive sink receipt. A lost acceptance response leaves shared history unadvanced; a later process safely retries the same key, allowing the sink to deduplicate the transport replay while Alsoul records one logical presentation. Presented still does not mean read, heard, or understood.

The adapter package contains provider-independent contracts, deterministic acceptance adapters, a generic HTTP world-acquisition adapter, an HTTPS JSON model adapter, and an HTTPS first-party presentation adapter. Model credentials remain transport-only configuration and are not inserted into ContextProjection, provider context, semantic response payloads, or presentation state.

`ConfiguredFoundationRuntime` closes the fixture-to-runtime boundary for the reactive slice. It requires configured HTTPS world/model/presentation routes, applies a source-origin-pinned JSON world interpreter before WorldResult admission, keeps runtime credentials separate from public configuration, exposes a synthetic model-contract probe, and provides content-free recovery diagnostics derived from canonical rows.

The process-facing runtime is exposed through `alsoul-host` and `python -m alsoul.host`. Host configuration version 2 requires the existing database plus explicit world, model, and first-party presentation routes. The host reads model authorization only from the process environment, validates existing persistence before opening runtime state, and exposes `ready`, `ingest`, `interact`, `diagnose`, `probe-model-contract`, and lower-level `respond`. It never creates schema or identity roots; bootstrap remains a separate administration boundary.

The process acceptance path admits a trusted current input in one process, resumes it in a later process, performs configured HTTPS world/model/presentation I/O, and verifies that replay after presentation does not duplicate the input, acquisition, generation, adoption, sink presentation, or Timeline presentation. It also verifies the harder uncertain-presentation case: the sink may accept an output and lose the response, after which a new process retries the same semantic key without false shared history or duplicate logical presentation.

The repository continuously verifies source/test compilation, the executable acceptance suite, process-level HTTPS runtime execution, and migration upgrade/downgrade.

See [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md), [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md), [F4 Controlled Provider Integration](docs/F4_CONTROLLED_PROVIDER_INTEGRATION.md), [F4 Provider Recovery Hardening](docs/F4_PROVIDER_RECOVERY_HARDENING.md), [F4 End-to-End Runtime Coordinator](docs/F4_RUNTIME_COORDINATOR.md), [F4 Configured Reactive Runtime](docs/F4_CONFIGURED_RUNTIME.md), [F4 Runtime Host](docs/F4_RUNTIME_HOST.md), [F4 Trusted First-Party Ingress](docs/F4_FIRST_PARTY_INGRESS.md), and [F4 First-Party Presentation Acceptance](docs/F4_FIRST_PARTY_PRESENTATION.md) for the executable foundation checkpoints.

## Documentation

Core documents:

- [Product Constitution](docs/PRODUCT_CONSTITUTION.md)
- [Architecture Convergence](docs/ARCHITECTURE_CONVERGENCE.md)
- [Foundation Walking Skeleton](docs/FOUNDATION_WALKING_SKELETON.md)
- [Decision Ledger](docs/DECISION_LEDGER.md)
- [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md)
- [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md)
- [F4 Controlled Provider Integration](docs/F4_CONTROLLED_PROVIDER_INTEGRATION.md)
- [F4 Provider Recovery Hardening](docs/F4_PROVIDER_RECOVERY_HARDENING.md)
- [F4 End-to-End Runtime Coordinator](docs/F4_RUNTIME_COORDINATOR.md)
- [F4 Configured Reactive Runtime](docs/F4_CONFIGURED_RUNTIME.md)
- [F4 Runtime Host](docs/F4_RUNTIME_HOST.md)
- [F4 Trusted First-Party Ingress](docs/F4_FIRST_PARTY_INGRESS.md)
- [F4 First-Party Presentation Acceptance](docs/F4_FIRST_PARTY_PRESENTATION.md)
- [Architecture Checkpoint — Decisions 11.A through 15.B](docs/ARCHITECTURE_CHECKPOINT_11_15.md)

Architecture decision records:

- [ADR-001 — Context and Output Boundary](docs/adr/ADR-001_CONTEXT_AND_OUTPUT.md)
- [ADR-002 — Authority, Action, Execution, and Effect](docs/adr/ADR-002_AUTHORITY_AND_EFFECTS.md)
- [ADR-003 — Durable Work, Commitments, Tasks, and Deliverables](docs/adr/ADR-003_DURABLE_WORK.md)
- [ADR-004 — World Signals, Triggers, and Proactive Initiation](docs/adr/ADR-004_PROACTIVITY.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](docs/adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](docs/adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)

## Status

Presentation-gated trusted first-party F4 interaction. The executable slice can accept an authenticated first-party transport assertion, recover the same counterpart/relationship/presence graph across process death, perform evidence-backed world acquisition and model generation, adopt one companion response, require actual first-party sink acceptance, and only then commit one canonical presented Timeline event. Unknown presentation outcomes remain unconfirmed and recover through the same stable semantic presentation key. Broader F2 domains remain architecturally specified but are deliberately not implemented in the walking skeleton yet.
