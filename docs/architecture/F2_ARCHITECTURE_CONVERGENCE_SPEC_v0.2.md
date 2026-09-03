# Alsoul F2 Architecture Convergence Specification

**PUBLICATION: GITHUB-SAFE**  
**Specification version:** 0.2  
**Prepared:** 2026-09-03  
**Gate:** F2 — Architecture Convergence  
**Status:** Working specification; supersedes v0.1

## 1. Normative basis

This version preserves the F2 v0.1 architecture except where this document or a linked closed F2 decision explicitly refines it.

Normative documents for the current F2 state:

- `F2_ARCHITECTURE_CONVERGENCE_SPEC_v0.2.md` — current convergence control specification;
- `F2_DECISION_01_COMPANION_PERSON.md` — closed `CompanionPerson` identity/ownership/lifecycle contract;
- `FUTURE_WORK.md` — reserved/deferred architecture that must remain possible without becoming current scope.

`F2_ARCHITECTURE_CONVERGENCE_SPEC_v0.1.md` is retained as historical architecture state. Where v0.1 wording conflicts with Decision 01, Decision 01 and this v0.2 specification are authoritative.

This specification does not authorize F3/F4 implementation.

---

## 2. F2 architectural center

```text
Person
  ↓
Historical Truth
  ↓
Evidence + Claims
  ↓
Epistemic Policy
  ↓
World Observation
  ↓
Interpretation
```

State classes remain:

```text
CANONICAL DURABLE STATE
DERIVED DURABLE STATE
RUNTIME STATE
PROJECTION STATE
```

Projection state never silently becomes canonical truth.

---

## 3. Decision 01 incorporated — `CompanionPerson`

**Status:** CLOSED

Minimum canonical domain object:

```text
CompanionPerson {
    person_id
    created_at
    lifecycle_state  // ACTIVE | ARCHIVED
}
```

Canonical rules:

```text
Identity is primitive, not inferred.
Continuity ≠ similarity.
Person evolution ≠ Person replacement.
Loss of faculty ≠ loss of Person.
Semantic ownership ≠ physical embedding.
Runtime instance ≠ Person.
State copy ≠ identity continuity.
```

The Person has these semantic relations:

```text
CompanionPerson
  ├── identity-owns continuity-bearing SelfModel
  ├── participates in RelationshipState
  ├── scopes/participates in canonical InteractionEvents
  ├── holds admitted MemoryClaims / PersonClaims
  └── binds replaceable faculties/contexts
```

The Person record does not require embedded references/arrays for Self, relationships, timeline, claims, PersonModel, or bindings.

### Identity

```text
PersonID ≠ ModelID ≠ SessionID ≠ ThreadID ≠ CredentialID ≠ BodyID
```

Model/provider/persona/thread/surface/channel/body/runtime/device/credential changes do not create another Person. A new Person requires explicit creation of a new `PersonID`.

### Self refinement

`SelfModel` is continuity-bearing canonical state distinct from Person identity.

```text
CONSTITUTIONAL
SLOWLY_MUTABLE
DERIVED_NARRATIVE
```

Freely mutable presentation/style/voice/avatar/surface adaptation belongs to Persona/Presentation, not SelfModel.

Exact Self fields remain open as Decision 02.

### Relationship refinement

`RelationshipState` is first-class relational state in which the Person participates. It is not intrinsic Person state, a PersonModel, memory bucket, history container, or interaction policy.

A new thread does not create a new relationship. Exact F4 relationship fields remain open.

### History refinement

Canonical history is represented by `InteractionEvent`s.

```text
Person Timeline
= ordered historical view over canonical Person-attributed/scoped InteractionEvents
```

A physically owned first-class Timeline object is not required for F4. `InteractionEvent ≠ EvidenceItem`.

### Memory/claim refinement

Person holds admitted claims semantically; claims remain independent canonical records.

```text
HOLDER ≠ SUBJECT ≠ APPLICABILITY SCOPE ≠ EPISTEMIC SOURCE/SUPPORT
```

A `PersonClaim` about a counterpart is Alsoul's admitted interpretation, not canonical state of that counterpart. `PersonModel` remains derived.

### Binding refinement

```text
BindingID ≠ PersonID
binding replacement → same PersonID
binding absence      → Person remains valid
credential available ≠ permission ≠ approval ≠ effect
rebinding            ≠ Person migration
```

Binding-local projections/configuration cannot become the sole canonical source of Self, Relationship, History, Evidence, Claims, or Person identity.

### Creation / reconstruction / lifecycle

A new Person exists when a new `PersonID` and minimum valid canonical `SelfModel` are committed. Provider/model/credential/relationship/thread/surface/channel/body availability is not required for Person creation.

Reconstruction loads an existing Person; it never creates replacement identity.

```text
load Person identity/lifecycle
↓ load minimum valid SelfModel
↓ resolve relevant RelationshipState
↓ load continuity-critical claims / needed PersonModel projection
↓ resolve canonical history revision
↓ attach available bindings
↓ permit cognition that depends on those continuity inputs
```

Missing continuity-bearing state must not be silently replaced with defaults and presented as successful continuity.

Person lifecycle is initially:

```text
ACTIVE
ARCHIVED
```

Binding/runtime failure states do not belong in Person lifecycle. Archive/reactivate preserves the same `PersonID`. Person erasure is a separately governed privacy/data operation and a `PersonID` is never reassigned.

Full normative Decision 01 detail and acceptance proofs are in `F2_DECISION_01_COMPANION_PERSON.md`.

---

## 4. Foundation object set after Decision 01

Foundation-required first-class semantics remain:

```text
CompanionPerson
SelfModel
RelationshipState
InteractionEvent
EvidenceItem
MemoryClaim
PersonClaim
Observation
WorldResult
ContextProjection
```

Required semantic components that may initially be embedded remain:

```text
PersonModel / CounterpartPersonModel
Persona / Presentation Profile
AffectState
Investigation
WorldSignal / Trigger
```

F4 also requires a replaceable `ModelBinding` and one read-only public-world search adapter.

Decision 01 does not add a new F4 subsystem.

---

## 5. Existing F2 contracts retained

### Evidence / claims

```text
Claim ↔ Evidence[]
```

Minimum claim statuses:

```text
ACTIVE
SUPERSEDED
RETRACTED
EXPIRED
```

Correction changes current claims/projections without rewriting historical evidence.

### Memory admission

All durable memory writes converge on:

```text
REJECT
ADMIT_AS_EVIDENCE_ONLY
ADMIT_MEMORY_CLAIM
ADMIT_PERSON_CLAIM
```

World observations do not automatically become memory. AI-generated statements cannot bootstrap external truth. Inferred PersonClaims require actual supporting evidence. Scope/privacy is explicit. Extensions/background paths cannot bypass admission.

### Epistemic source

Minimum source kinds remain:

```text
SELF
MEMORY
INFERENCE
OBSERVATION
SEARCH_RESULT
TOOL_RESULT
OTHER_PERSON
```

Epistemic source is independent from ownership/visibility scope and constrains admissible use.

### Context projection

`ContextProjection` is rebuildable/discardable and never canonical history. It must identify sufficient source revision/input state to reject stale derived work:

```text
derivation starts at R1
source becomes R2
R1 result returns
→ reject / rebase / recompute
```

### World interface

F4 remains read-only public-world access:

```text
need current/external fact
↓ Observation / search
↓ WorldResult + EvidenceItem(s)
↓ result presentation
↓ Alsoul interpretation using remembered/person context
```

`Observation ≠ MemoryClaim` and `WorldResult ≠ Companion Interpretation`.

---

## 6. Reserved future seams

These remain semantically separated but outside F4 implementation:

```text
Capability
CredentialBinding
Permission
Approval
Action / Effect
ConversationOpenLoop
DelegatedTask
WorkRun / ExecutionAttempt
Commitment
Skill / Procedure
WorkArtifact / WorkProduct
SurfaceBinding
ChannelBinding
EmbodimentBinding
```

Authority, work, and presence reservations remain governed by `FUTURE_WORK.md` and do not become planned-next work merely by being preserved.

---

## 7. F4 minimum subset — unchanged

Required:

```text
CompanionPerson
SelfModel (minimal)
RelationshipState (minimal)
InteractionEvent canonical history
EvidenceItem
MemoryClaim
PersonClaim specialization
PersonModel projection (minimal)
Epistemic source metadata
Observation
WorldResult
ContextProjection
ModelBinding
one read-only search adapter
```

Still excluded:

```text
full affect engine
commitments
workers/subagents
durable WorkRun
skills/procedural learning
personal connectors
write/action authority
voice
avatar/body
ambient presence
cryptographic Person principal
portable-Person protocol
plugin marketplace
organization/multi-agent institution
```

---

## 8. Decision 01 acceptance proofs added to F3 target

In addition to the v0.1 evidence/memory/world/projection tests, F3 must prove:

```text
replace model/provider
→ same PersonID, Self, Relationship, history, claims

replace persona/presentation
→ same PersonID and SelfModel

remove credential
→ Person/Self/Relationship/history survive
→ cognition becomes unbound

new thread/surface/channel/runtime/device
→ same PersonID
→ no implicit new relationship

valid SelfModel revision
→ same PersonID

archive then reactivate
→ same PersonID and canonical state

explicit state fork into a new Person
→ new PersonID
```

Recovery must prove:

```text
persist canonical Person/Self/Relationship/history/claims
kill process and discard runtime/model context
reconstruct existing PersonID
hydrate required continuity state before dependent cognition
attach available bindings only after canonical reconstruction
→ same semantic Person
```

Failure cases:

```text
required SelfModel missing/corrupt
→ do not substitute default Self and claim continuity

provider initialization fails
→ Person still reconstructs
→ cognition binding remains unavailable
```

---

## 9. Explicit F2 decisions through Decision 01

1. Person is the primitive identity root; `PersonID` is immutable.
2. Minimum Person state is `person_id`, `created_at`, `lifecycle_state` with `ACTIVE | ARCHIVED`.
3. Creation and reconstruction are distinct; reconstruction preserves existing `PersonID`.
4. SelfModel is continuity-bearing state; freely mutable presentation is separate.
5. Person participates in first-class RelationshipState.
6. Canonical history is InteractionEvent-based; timeline is an ordered view.
7. Person holds independent admitted claims; PersonModel is derived.
8. Claim holder, subject, scope, and source/support are independent.
9. Replaceable bindings/contexts/infrastructure do not own Person identity.
10. Binding failure/absence does not invalidate Person existence.
11. Credentials do not imply authority.
12. Archive/reactivate preserves identity; erasure is separately governed; PersonID is never reassigned.
13. Canonical history remains separate from model context.
14. EvidenceItem is first-class when load-bearing.
15. PersonClaim may share storage with MemoryClaim while remaining semantically distinct.
16. Claims support one-or-more evidence links.
17. PersonModel is a projection, not source of truth.
18. Memory admission is centralized.
19. Epistemic source is separate from memory scope/visibility.
20. Source kind constrains admissible use.
21. Observation/WorldResult mediate external information.
22. Simple F4 search does not require durable Investigation.
23. ContextProjection is rebuildable/discardable.
24. Hydration precedes cognition that depends on continuity state.
25. Authority/work/presence seams remain deferred from F4.
26. F4 remains read-only public-world access.

---

## 10. Remaining F2 decisions

Decision 01 is closed. Eleven bounded decisions remain:

1. exact constitutional vs slowly mutable `SelfModel` fields;
2. exact `RelationshipState` minimum for F4;
3. concrete first-slice `PersonClaim` kind vocabulary;
4. support-validation policy for inferred PersonClaims;
5. memory-admission categories and default retention policy;
6. F4 freshness vocabulary/classes;
7. exact `ContextProjection` source-revision representation;
8. exact recovery package/repository boundaries;
9. user-facing memory correction/inspection semantics required by F3;
10. whether F4 affect is entirely runtime or minimally durable;
11. precise `InteractionEvent` content versus separately retained `EvidenceItem` boundary.

None may widen F4.

---

## 11. Next decision

Proceed to **F2 Decision 02 — exact `SelfModel` contract** using the `Problem → First Principle → Solution` method.

F3/F4 implementation remains unauthorized until F2 closes.