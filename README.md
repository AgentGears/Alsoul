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
schema initialization ≠ identity bootstrap ≠ runtime recovery
surface operational state ≠ canonical companion state
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
    admin/
    adapters/
    domain/
    host/
    migrations/
    services/
    storage/
    surface/
```

Packaged database migrations live under `src/alsoul/migrations/`, and executable architecture tests live under `tests/`.

First-run administration is explicit through `alsoul-admin` and `FoundationAdministrator`. `initialize-store` creates only a new schema store, `migrate-store` advances an existing store to the packaged migration head, `status` derives content-free administration state, and `bootstrap-foundation` creates the one-time F4 Person/Counterpart/Relationship identity graph. Existing database paths are never overwritten by initialization, schema migration is never an implicit runtime side effect, and partially existing canonical identity blocks bootstrap rather than being silently repaired.

Foundation identity creation remains isolated in `FoundationBootstrapper`; ordinary `FoundationServices` and `alsoul-host` fail closed rather than recreating missing Person/Relationship roots. A schema-ready but identity-empty store can pass structural host readiness while trusted ingress still fails identity resolution without creating any replacement identity.

Trusted first-party ingress is explicit through `FirstPartyIngress`. An authenticated transport assertion resolves only pre-existing CounterpartIdentityBinding, RelationshipState, SurfaceBinding, and ChannelBinding state before it can become a canonical `COUNTERPART_INPUT`. The model never participates in identity resolution, unknown identity fails closed, and semantic transport-event replay collapses to one Timeline event.

Provider execution is routed through Alsoul-owned orchestration boundaries. `WorldAcquisitionRunner` persists an Observation before a replaceable acquisition adapter runs and stops at captured evidence; `ModelGenerationRunner` persists ModelInvocation before dispatch and stops at GeneratedOutput. Neither path can bypass WorldResult admission, CompanionOutput adoption, or presentation.

Provider recovery is explicit. `RecoveryCoordinator` derives `MODEL_ATTEMPT_UNRESOLVED` for orphaned in-progress generation, `ProviderRecoveryCoordinator` can conservatively reconcile a known process-lost attempt to `UNKNOWN`, and the semantic service boundary prevents blind retry, stale ContextProjection reuse, and regeneration when a durable GeneratedOutput already exists.

Reactive orchestration is composed through `FoundationResponseCoordinator`. It derives progress from canonical rows, reuses already-durable Investigation/Capture/WorldResult/ContextProjection/GeneratedOutput state, and resumes after process death from the furthest trustworthy semantic boundary without persisting a parallel turn-status aggregate.

First-party presentation is an explicit acceptance boundary. The coordinator derives a restart-stable semantic presentation key from the adopted `CompanionOutput` and exact surface/channel route, sends the exact content and digest through a provider-independent presentation adapter, and commits `COMPANION_PRESENTED_OUTPUT` only after validating a positive sink receipt. A lost acceptance response leaves shared history unadvanced; a later process safely retries the same key, allowing the sink to deduplicate the transport replay while Alsoul records one logical presentation. Presented still does not mean read, heard, or understood.

The adapter package contains provider-independent contracts, deterministic acceptance adapters, a generic HTTP world-acquisition adapter, an HTTPS JSON model adapter, and an HTTPS first-party presentation adapter. Model credentials remain transport-only configuration and are not inserted into ContextProjection, provider context, semantic response payloads, or presentation state.

`ConfiguredFoundationRuntime` closes the fixture-to-runtime boundary for the reactive slice. It requires configured HTTPS world/model/presentation routes, applies a source-origin-pinned JSON world interpreter before WorldResult admission, keeps runtime credentials separate from public configuration, exposes a synthetic model-contract probe, and provides content-free recovery diagnostics derived from canonical rows.

The process-facing runtime is exposed through `alsoul-host` and `python -m alsoul.host`. Host configuration version 2 requires the existing database plus explicit world, model, and first-party presentation routes. The host reads model authorization only from the process environment, validates existing persistence before opening runtime state, and exposes `ready`, `ingest`, `interact`, `diagnose`, `probe-model-contract`, and lower-level `respond`. It never initializes schema or identity roots; those are separate administration operations.

A minimal local first-party web surface is exposed through `alsoul-surface` and `python -m alsoul.surface`. It binds only to `127.0.0.1`, uses an operator-configured existing identity/surface/channel route, and sends every message through `FirstPartyIngress` plus the configured reactive runtime. The browser layer performs no canonical semantic writes. A separate local surface-state database preserves exact inbound transport replay semantics and presentation acceptance across surface-process replacement while remaining explicitly non-canonical. The browser API returns only user-facing content and transport replay state, not internal Person/Relationship/cognition identifiers.

The local presentation sink reuses the existing semantic presentation-key contract. Exact acceptance is persisted before the runtime commits `COMPANION_PRESENTED_OUTPUT`; exact replay returns the same acceptance, and semantic key reuse with different content is rejected. The local surface's operational state is therefore not a second Timeline or memory system—it exists only to make the local transport/presentation boundary restart-idempotent.

The process acceptance path admits a trusted current input in one process, resumes it in a later process, performs configured HTTPS world/model/presentation I/O, and verifies that replay after presentation does not duplicate the input, acquisition, generation, adoption, sink presentation, or Timeline presentation. It also verifies the harder uncertain-presentation case: the sink may accept an output and lose the response, after which a new process retries the same semantic key without false shared history or duplicate logical presentation.

The administration acceptance path separately proves a clean first run: a new store is initialized and migrated, foundation identity is explicitly bootstrapped in a later process, and ordinary runtime presented with an identity-empty store refuses ingress without manufacturing Person, CounterpartPerson, or RelationshipState.

The local-surface acceptance path proves that closing one complete surface/runtime composition and constructing another over the same canonical database and local surface state preserves the same Person, counterpart, RelationshipState, input event, CompanionOutput, and presented Timeline event. Replaying the same local transport event performs no second world acquisition or model generation and does not create a second local presentation acceptance.

The repository continuously verifies source/test compilation, the executable acceptance suite, process-level runtime/administration/local-surface behavior, and migration upgrade/downgrade.

See [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md), [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md), [F4 Controlled Provider Integration](docs/F4_CONTROLLED_PROVIDER_INTEGRATION.md), [F4 Provider Recovery Hardening](docs/F4_PROVIDER_RECOVERY_HARDENING.md), [F4 End-to-End Runtime Coordinator](docs/F4_RUNTIME_COORDINATOR.md), [F4 Configured Reactive Runtime](docs/F4_CONFIGURED_RUNTIME.md), [F4 Runtime Host](docs/F4_RUNTIME_HOST.md), [F4 Trusted First-Party Ingress](docs/F4_FIRST_PARTY_INGRESS.md), [F4 First-Party Presentation Acceptance](docs/F4_FIRST_PARTY_PRESENTATION.md), [F4 Administration and First-Run Bootstrap](docs/F4_ADMINISTRATION.md), and [F4 Local First-Party Surface](docs/F4_LOCAL_FIRST_PARTY_SURFACE.md) for the executable foundation checkpoints.

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
- [F4 Administration and First-Run Bootstrap](docs/F4_ADMINISTRATION.md)
- [F4 Local First-Party Surface](docs/F4_LOCAL_FIRST_PARTY_SURFACE.md)
- [Architecture Checkpoint — Decisions 11.A through 15.B](docs/ARCHITECTURE_CHECKPOINT_11_15.md)

Architecture decision records:

- [ADR-001 — Context and Output Boundary](docs/adr/ADR-001_CONTEXT_AND_OUTPUT.md)
- [ADR-002 — Authority, Action, Execution, and Effect](docs/adr/ADR-002_AUTHORITY_AND_EFFECTS.md)
- [ADR-003 — Durable Work, Commitments, Tasks, and Deliverables](docs/adr/ADR-003_DURABLE_WORK.md)
- [ADR-004 — World Signals, Triggers, and Proactive Initiation](docs/adr/ADR-004_PROACTIVITY.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](docs/adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](docs/adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)

## Status

Locally usable, explicitly initializable, presentation-gated trusted first-party F4 interaction. A fresh installation can create and migrate a new store through a separate administration process, bootstrap the initial durable identity graph exactly once, and then hand control to the ordinary runtime. The reactive slice can accept trusted first-party input, recover the same counterpart/relationship/presence graph across process death, perform evidence-backed world acquisition and model generation, adopt one companion response, require first-party sink acceptance, and only then commit one canonical presented Timeline event. A loopback browser surface now sits in front of those same boundaries without becoming a second identity, cognition, memory, or persistence authority. Missing identity remains a hard runtime failure rather than an implicit bootstrap trigger. Broader F2 domains remain architecturally specified but are deliberately not implemented in the walking skeleton yet.
