# Alsoul

> **A companion with a world, not a chatbot with tools.**

Alsoul is a persistent personal companion architecture designed to remain one continuous person across model, process, thread, surface, channel, and provider changes.

The project is in **foundation implementation**. The semantic backbone is converged through identity, history, memory, fresh-world access, cognition/output, authority/effects, durable delegated work, proactivity, presence/modality, presentation policy, conversational open loops, recovery, and the F4 persistence/application-service boundary. The executable F4 slice is intentionally narrower than the full architecture.

## Product thesis

Alsoul should feel like someone who knows you, lives in your world, and knows the limits of what they know and can do.

The primary trust quality is **felt honesty**. When Alsoul says it remembers, checked, observed, inferred, acted, scheduled, produced, delivered, presented, or is uncertain, those words should correspond to real internal state.

```text
                    Alsoul
                      │
       ┌──────────────┼──────────────┐
       │              │              │
   knows me       has a world      can help me
       │              │              │
   remembers        can check      can act
   understands      can observe    can work
   our history      can notice     can follow up
```

## Foundation principles

```text
Companion ≠ Model
Self ≠ Relationship ≠ World
Memory ≠ Observation
Historical Evidence ≠ Derived Memory
Observation ≠ Interpretation
Search result ≠ Companion belief
Person ≠ Thread ≠ Surface ≠ Channel ≠ Embodiment
Relationship ≠ Provider Endpoint
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
interaction classification ≠ model authority
memory statement ≠ fresh-world question ≠ conversational response
memory admission ≠ response obligation
conversation ≠ fresh-world investigation
conversation ≠ memory admission
Timeline history ≠ MemoryClaim
prior Timeline context ≠ factual source authority
reference resolution ≠ unrestricted transcript injection
source-free expression ≠ evidence-backed proposition
surface notice ≠ CompanionOutput
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

Canonical state selected for cognition
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
```

The wider architecture also defines capability/credential/permission/action/effect semantics, delegated work, commitments, triggers, WorkRuns, WorkProducts, WorldSignals, proactivity, modality, presentation policy, conversational open loops, and whole-system recovery. Those are not all implemented in F4.

## Executable F4 interaction paths

Trusted first-party input is always admitted to canonical history before semantic routing:

```text
trusted first-party ingress
↓
COUNTERPART_INPUT
↓
F4InteractionPurposeGate
├── MEMORY_STATEMENT
│   ↓
│   bounded candidate / proposal
│   ↓
│   EvidenceItem + admitted Claim
│   ↓
│   stop without fabricated Companion speech
│
├── CONVERSATIONAL_RESPONSE
│   ↓
│   ContextProjection
│       Self + Relationship + current input
│       optional one bounded immediately-prior presented exchange
│       no projected personal/world proposition
│   ↓
│   ModelInvocation
│   ↓
│   GeneratedOutput(COMPANION_EXPRESSION)
│   ↓
│   explicit adoption
│   ↓
│   first-party presentation acceptance
│   ↓
│   COMPANION_PRESENTED_OUTPUT
│
└── WORLD_QUESTION
    ↓
    recover eligible personal memory
    ↓
    fresh Investigation / Observation / WorldSourceCapture
    ↓
    EvidenceItem / WorldResult
    ↓
    ContextProjection with exact provenance
    ↓
    ModelInvocation / GeneratedOutput
    ↓
    explicit CompanionOutput adoption
    ↓
    first-party presentation acceptance
    ↓
    COMPANION_PRESENTED_OUTPUT
```

Everything outside the bounded implemented grammar remains `UNSUPPORTED` after canonical ingress. The model does not decide which branch runs.

The checked path is mechanically capable of meaning:

```text
"You told me ..."
"I checked ..."
"My take is ..."
```

without those distinctions being prompt conventions.

The conversational path supports bounded self-contained social forms and a narrow contextual grammar that can reference exactly the immediately preceding presented exchange. Broader pronoun/coreference resolution, generic transcript windows, semantic Timeline search, and cross-thread/channel references remain unsupported.

## Implementation boundaries

The source tree is organized around semantic ownership rather than provider APIs:

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

### Administration

First-run administration is explicit through `alsoul-admin` and `FoundationAdministrator`.

```text
package installation
≠ schema initialization
≠ schema migration
≠ CompanionPerson bootstrap
≠ counterpart/relationship binding
≠ ordinary runtime
```

`initialize-store` creates a new schema store, `migrate-store` advances an existing store, `status` derives administration state, and `bootstrap-foundation` creates the initial F4 identity graph. Ordinary runtime never silently recreates missing identity roots.

### Trusted ingress

`FirstPartyIngress` resolves only pre-existing CounterpartIdentityBinding, RelationshipState, SurfaceBinding, and ChannelBinding state before appending one canonical `COUNTERPART_INPUT`. The model never participates in identity resolution. Semantic transport-event replay collapses to one Timeline event.

### Evidence-grounded memory

`F4CounterpartMemoryAdmission` currently recognizes only the bounded `primary_machine.memory_gb` predicate. It separates:

```text
counterpart statement
≠ extracted candidate
≠ memory proposal
≠ admitted memory
```

Correction is append-only through explicit supersession. Concurrent admission is fenced so one singleton predicate does not acquire multiple uncontested current claims.

### Interaction-purpose routing

`F4InteractionPurposeGate` classifies only canonical input and is deterministic/provider-independent. It currently selects `MEMORY_STATEMENT`, `CONVERSATIONAL_RESPONSE`, `WORLD_QUESTION`, or `UNSUPPORTED`.

`ConfiguredFoundationRuntime.interact` is the high-level semantic boundary. `ConfiguredFoundationRuntime.respond` remains a lower-level checked-response primitive and rejects any canonical input that is not a `WORLD_QUESTION` before provider work.

### Conversational response

`FoundationConversationalResponseCoordinator` handles the bounded source-free conversational path. Self-contained forms project canonical Self/Relationship/current-input state. The narrow contextual grammar may additionally project exactly the immediately preceding completed presented exchange as historical interaction context. Neither path performs Investigation or memory admission, and both require exactly one unsourced `COMPANION_EXPRESSION` before explicit conversational adoption.

```text
conversation context ≠ canonical history
Timeline context ≠ admitted memory
prior Companion speech ≠ factual source authority
provider session ≠ Relationship continuity
source-free expression ≠ memory/world claim
GeneratedOutput ≠ CompanionOutput
```

The selected prior exchange is persisted as exact `context_projection_event` membership. Once the projection commits, recovery reuses those exact events rather than searching history again.

### Fresh-world checked response

`FoundationResponseCoordinator` preserves the F4 checked chain:

```text
Investigation
→ Observation
→ WorldSourceCapture
→ EvidenceItem
→ WorldResult
→ ContextProjection
→ ModelInvocation
→ GeneratedOutput
→ CompanionOutput
→ presentation
```

`WorldAcquisitionRunner` persists an Observation before external acquisition. Raw returned bytes become a recoverable capture first; a bounded extractor only proposes a WorldResult, and semantic admission independently validates lineage.

### Provider execution and recovery

Model execution is replaceable. `ModelInvocation` is committed before dispatch. Provider failure, unknown outcome, retry, and replacement do not redefine CompanionPerson.

`RecoveryCoordinator` derives progress from canonical rows instead of a mutable turn-status aggregate. Orphaned in-progress provider work is reconciled explicitly; retry creates a new attempt rather than mutating historical execution.

Provider rendering is versioned. The bounded prior-Timeline context checkpoint advances the renderer identity because contextual projections may now render a separate `prior_timeline_context` field while self-contained and checked projections retain their existing semantic contents.

### First-party presentation

A generated candidate is not automatically Companion speech. Both conversational and checked responses follow:

```text
GeneratedOutput
→ CompanionOutput adoption
→ presentation attempt
→ sink acceptance
→ COMPANION_PRESENTED_OUTPUT
```

The presentation key is restart-stable for the exact adopted output and route. A sink may deduplicate transport replay while Alsoul commits one logical Timeline presentation. Presented still does not mean read, heard, or understood.

### Configured runtime and host

`ConfiguredFoundationRuntime` composes world/model/presentation routes with canonical semantic services. Configuration and credentials remain outside companion identity and memory.

The process-facing runtime is exposed through `alsoul-host` / `python -m alsoul.host` with:

```text
ready
ingest
interact
diagnose
probe-model-contract
respond
```

`interact` uses the same semantic purpose gate as the local surface. `respond` is intentionally limited to the checked `WORLD_QUESTION` path.

### Local first-party surface

`alsoul-surface` / `python -m alsoul.surface` provides a loopback-only browser surface over the same trusted ingress and runtime boundaries. The browser does not decide identity, memory, purpose, contextual selection, cognition, or canonical persistence.

A separate local operational store owns only inbound transport replay and first-party presentation acceptance. It is not a second Timeline or memory system.

Memory-only acknowledgement appears as operational UI status rather than a Companion message. Conversational and checked responses appear as Companion messages only after presentation acceptance and canonical presentation succeed.

## Recovery guarantees exercised by F4

The executable suite exercises complete process/surface replacement and preserves the furthest durable semantic stage.

```text
Observation STARTED + process loss
→ retry creates a new Observation

ModelInvocation IN_PROGRESS + process loss
→ reconcile old attempt to UNKNOWN
→ retry creates a new ModelInvocation

ContextProjection with selected prior Timeline events committed
→ recover exact selection; do not search history again

GeneratedOutput committed
→ recover candidate; do not regenerate

CompanionOutput adopted
→ present existing adopted output

presentation already committed
→ return existing Timeline event; do not present again
```

The same response recovery graph is used by both source-free conversational responses and evidence-bearing checked responses; only the projection/output contract differs.

## Documentation

Core architecture:

- [Product Constitution](docs/PRODUCT_CONSTITUTION.md)
- [Architecture Convergence](docs/ARCHITECTURE_CONVERGENCE.md)
- [Foundation Walking Skeleton](docs/FOUNDATION_WALKING_SKELETON.md)
- [Decision Ledger](docs/DECISION_LEDGER.md)
- [Architecture Checkpoint — Decisions 11.A through 15.B](docs/ARCHITECTURE_CHECKPOINT_11_15.md)

Executable F4 checkpoints:

- [F4 Implementation Bootstrap](docs/F4_IMPLEMENTATION_BOOTSTRAP.md)
- [F4 Implementation Hardening](docs/F4_IMPLEMENTATION_HARDENING.md)
- [F4 Controlled Provider Integration](docs/F4_CONTROLLED_PROVIDER_INTEGRATION.md)
- [F4 Provider Recovery Hardening](docs/F4_PROVIDER_RECOVERY_HARDENING.md)
- [F4 End-to-End Runtime Coordinator](docs/F4_RUNTIME_COORDINATOR.md)
- [F4 Configured Runtime](docs/F4_CONFIGURED_RUNTIME.md)
- [F4 Runtime Host](docs/F4_RUNTIME_HOST.md)
- [F4 Trusted First-Party Ingress](docs/F4_FIRST_PARTY_INGRESS.md)
- [F4 First-Party Presentation Acceptance](docs/F4_FIRST_PARTY_PRESENTATION.md)
- [F4 Administration and First-Run Bootstrap](docs/F4_ADMINISTRATION.md)
- [F4 Local First-Party Surface](docs/F4_LOCAL_FIRST_PARTY_SURFACE.md)
- [F4 Evidence-Grounded Memory Admission](docs/F4_EVIDENCE_GROUNDED_MEMORY_ADMISSION.md)
- [F4 Interaction Purpose Gate](docs/F4_INTERACTION_PURPOSE_GATE.md)
- [F4 Conversational Response Path](docs/F4_CONVERSATIONAL_RESPONSE.md)
- [F4 Prior-Timeline Context Selection](docs/F4_PRIOR_TIMELINE_CONTEXT.md)

Architecture decision records:

- [ADR-001 — Context and Output Boundary](docs/adr/ADR-001_CONTEXT_AND_OUTPUT.md)
- [ADR-002 — Authority, Action, Execution, and Effect](docs/adr/ADR-002_AUTHORITY_AND_EFFECTS.md)
- [ADR-003 — Durable Work, Commitments, Tasks, and Deliverables](docs/adr/ADR-003_DURABLE_WORK.md)
- [ADR-004 — World Signals, Triggers, and Proactive Initiation](docs/adr/ADR-004_PROACTIVITY.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](docs/adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](docs/adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)

## Status

The canonical foundation now supports explicit first-run initialization, durable identity, trusted first-party ingress, evidence-grounded bounded memory, deterministic semantic routing, bounded source-free conversational response, mechanically bounded immediate-prior Timeline context, fresh-world checked response, provider execution/recovery, explicit output adoption, restart-safe first-party presentation, and a loopback browser surface.

F4 deliberately does **not** yet implement general conversational routing, arbitrary prior-history reference resolution, generic transcript windows, semantic Timeline search, general question answering, arbitrary fresh-world questions, broad memory extraction, effectful Actions, durable delegated work, scheduling, proactivity, multi-channel fallback, read/heard receipts, or rich embodiment.

The next implementation work should widen only one semantic boundary at a time without collapsing the distinctions above.
