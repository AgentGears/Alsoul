# Alsoul

> **A companion with a world, not a chatbot with tools.**

Alsoul is a persistent personal companion architecture designed to remain one continuous person across model, process, thread, surface, channel, and provider changes.

The project is in **foundation implementation**. The semantic backbone is converged through identity, history, memory, fresh-world access, cognition/output, authority/effects, durable delegated work, proactivity, presence/modality, presentation policy, conversational continuity, recovery, and the F4 persistence/application-service boundary. The executable F4 slice remains intentionally narrower than the full architecture.

## Product thesis

Alsoul should feel like someone who knows you, lives in your world, and knows the limits of what they know and can do.

The primary trust quality is **felt honesty**. When Alsoul says it remembers, checked, observed, inferred, acted, scheduled, produced, delivered, presented, or is uncertain, those words should correspond to real internal state.

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
ConversationOpenLoop ≠ MemoryClaim ≠ DelegatedTask ≠ Commitment ≠ Trigger
open_loop_id ≠ open_loop_reference_id ≠ reference key ≠ selector
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
open conversational matter ≠ background-work authority
reference resolution ≠ unrestricted transcript injection
exact open-loop addressing ≠ semantic history search
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
            ├── ConversationOpenLoop
            │       └── ConversationOpenLoopReference
            │
            └── Canonical Timeline
                    │
                    └── EvidenceItem
                            │
                            └── MemoryClaim / PersonClaim

Fresh world question
    │
    └── Investigation
            └── Observation
                    └── WorldSourceCapture
                            └── EvidenceItem
                                    └── WorldResult

Canonical state selected for cognition
    │
    └── ContextProjection
            └── ModelInvocation
                    └── GeneratedOutput
                            └── CompanionOutput
                                    └── presentation acceptance
                                            └── presented Timeline event
```

The wider architecture also defines capability/credential/permission/action/effect semantics, delegated work, commitments, triggers, WorkRuns, WorkProducts, WorldSignals, proactivity, modality, presentation policy, richer conversational continuity, and whole-system recovery. Those are not all implemented in F4.

## Executable F4 interaction paths

Trusted first-party input is admitted to canonical history before semantic routing:

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
│   optional bounded ConversationOpenLoop transition
│   ↓
│   deterministic context selection
│       self-contained current input
│       OR immediately-prior presented exchange
│       OR one host-resolved DECISION ConversationOpenLoop
│   ↓
│   ContextProjection
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

Everything outside the bounded implemented grammar remains `UNSUPPORTED` after canonical ingress. The model does not decide which branch runs or which durable open loop a reference means.

The checked path can mechanically support distinctions such as:

```text
"You told me ..."
"I checked ..."
"My take is ..."
```

without relying on prompt convention.

## Conversational continuity

The source-free conversational path supports bounded self-contained social forms, exact immediately-prior presented-exchange context, and durable relationship-scoped `DECISION` open loops.

Decision-loop opening is durable:

```text
"I need to decide between A and B."
↓
ConversationOpenLoop OL1
+
ConversationOpenLoopReference LR1
```

Unqualified reference remains fail-closed when more than one decision is active:

```text
"Back to that decision."
↓
0 active loops  → unavailable
1 active loop   → select it
>1 active loops → ambiguous
```

Decision 13.B adds deterministic explicit addressing:

```text
OL1 → ["a","b"]
OL2 → ["c","d"]

"Back to the decision between B and A."
↓
exact mechanical reference match
↓
OL1
```

The option-pair contract uses only Unicode normalization, whitespace normalization, case folding, and order-independent pair canonicalization. It does not use embeddings, synonyms, paraphrase inference, recency, semantic ranking, or model choice. Different loops may share the same reference key; such a collision is ambiguous rather than an identity merge.

Qualified references can govern bounded resume, resolve, and cancel operations. They do not create memory, work, permission, scheduling, or proactive-contact authority.

Successful loop selection is pinned into immutable `ContextProjection` provenance. Recovery reuses that exact selection rather than searching history again. Unqualified reuse requires continued global active-loop uniqueness; explicit reuse requires continued uniqueness only among loops matching the pinned reference, so unrelated loops do not invalidate it.

Broader pronoun/coreference resolution, generic transcript windows, semantic Timeline search, and arbitrary history resolution remain unsupported.

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

Ordinary runtime never silently recreates missing identity roots.

### Trusted ingress

`FirstPartyIngress` resolves only pre-existing CounterpartIdentityBinding, RelationshipState, SurfaceBinding, and ChannelBinding state before appending one canonical `COUNTERPART_INPUT`. The model never participates in identity resolution. Semantic transport-event replay collapses to one Timeline event.

### Evidence-grounded memory

`F4CounterpartMemoryAdmission` currently recognizes only the bounded `primary_machine.memory_gb` predicate and preserves:

```text
counterpart statement
≠ extracted candidate
≠ memory proposal
≠ admitted memory
```

Correction is append-only through explicit supersession. Concurrent admission is fenced so one singleton predicate does not acquire multiple uncontested current claims.

### Interaction-purpose routing

`F4InteractionPurposeGate` is deterministic/provider-independent and currently selects `MEMORY_STATEMENT`, `CONVERSATIONAL_RESPONSE`, `WORLD_QUESTION`, or `UNSUPPORTED`.

`ConfiguredFoundationRuntime.interact` is the high-level semantic boundary. The lower-level checked `respond` primitive rejects canonical input that is not a `WORLD_QUESTION` before provider work.

### Provider execution and recovery

Model execution is replaceable. `ModelInvocation` is committed before dispatch. Provider failure, unknown outcome, retry, and replacement do not redefine CompanionPerson.

`RecoveryCoordinator` derives progress from canonical rows rather than mutable turn status. Orphaned in-progress provider work is reconciled explicitly; retry creates a new attempt rather than mutating historical execution.

Provider rendering is versioned. Existing prior-Timeline and unqualified open-loop provider-context contracts use `f4-renderer-v3`. An explicit Decision 13.B open-loop reference changes the provider-context shape and therefore records `f4-renderer-v4`.

### Fresh-world checked response

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

Raw returned bytes become a recoverable capture before a bounded extractor proposes a WorldResult; semantic admission independently validates lineage.

### First-party presentation

```text
GeneratedOutput
→ CompanionOutput adoption
→ presentation attempt
→ sink acceptance
→ COMPANION_PRESENTED_OUTPUT
```

Presentation is restart-idempotent and remains distinct from read, heard, or understood.

### Configured runtime and local surface

`ConfiguredFoundationRuntime` composes world/model/presentation routes with canonical semantic services. Configuration and credentials remain outside companion identity and memory.

The process-facing host exposes:

```text
ready
ingest
interact
diagnose
probe-model-contract
respond
```

`alsoul-surface` provides a loopback-only browser surface over the same ingress/runtime boundaries. A separate local operational store owns transport replay and first-party presentation acceptance only; it is not a second Timeline or memory system.

## Recovery guarantees exercised by F4

```text
Observation STARTED + process loss
→ retry creates a new Observation

ModelInvocation IN_PROGRESS + process loss
→ reconcile old attempt to UNKNOWN
→ retry creates a new ModelInvocation

ContextProjection with selected prior Timeline events
→ recover exact selection; do not search history again

ContextProjection with unqualified ConversationOpenLoop selection
→ reuse only while selected loop remains the sole active DECISION loop

ContextProjection with explicit open-loop reference selection
→ reuse while selected loop remains the sole active loop matching the pinned reference
→ unrelated active loops do not invalidate it

GeneratedOutput committed
→ recover candidate; do not regenerate

CompanionOutput adopted
→ present existing adopted output

presentation already committed
→ return existing Timeline event; do not present again
```

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
- [F4 Conversation Open Loop](docs/F4_CONVERSATION_OPEN_LOOP.md)
- [F4 Targetable Conversation Open Loop](docs/F4_TARGETABLE_CONVERSATION_OPEN_LOOP.md)

Architecture decision records:

- [ADR-001 — Context and Output Boundary](docs/adr/ADR-001_CONTEXT_AND_OUTPUT.md)
- [ADR-002 — Authority, Action, Execution, and Effect](docs/adr/ADR-002_AUTHORITY_AND_EFFECTS.md)
- [ADR-003 — Durable Work, Commitments, Tasks, and Deliverables](docs/adr/ADR-003_DURABLE_WORK.md)
- [ADR-004 — World Signals, Triggers, and Proactive Initiation](docs/adr/ADR-004_PROACTIVITY.md)
- [ADR-005 — Presence, Presentation Policy, Conversational Continuity, and Recovery](docs/adr/ADR-005_PRESENCE_POLICY_AND_RECOVERY.md)
- [ADR-006 — F4 Persistence and Application-Service Boundary](docs/adr/ADR-006_F4_PERSISTENCE_AND_SERVICES.md)

## Status

The canonical foundation supports explicit first-run initialization, durable identity, trusted first-party ingress, evidence-grounded bounded memory, deterministic semantic routing, bounded source-free conversation, mechanically bounded immediate-prior Timeline context, durable relationship-scoped `DECISION` ConversationOpenLoops, exact source-grounded option-pair addressing, fresh-world checked response, provider execution/recovery, explicit output adoption, restart-safe first-party presentation, and a loopback browser surface.

F4 deliberately does **not** yet implement general conversational routing, arbitrary prior-history resolution, generic transcript windows, semantic Timeline search, semantic open-loop reference matching, general question answering, arbitrary fresh-world questions, broad memory extraction, automatic open-loop expiry/supersession, effectful Actions, durable delegated work, scheduling, proactivity, multi-channel fallback, read/heard receipts, or rich embodiment.

The next implementation work should widen only one semantic boundary at a time without collapsing the distinctions above.
