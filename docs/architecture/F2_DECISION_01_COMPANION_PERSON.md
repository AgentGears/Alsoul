# F2 Decision 01 — CompanionPerson Contract

**PUBLICATION: GITHUB-SAFE**  
**Status:** CLOSED  
**Gate:** F2 — Architecture Convergence  
**Prepared:** 2026-09-03

## Decision

`CompanionPerson` is the primitive canonical identity root of one Alsoul person. Identity is asserted by canonical state, never inferred from model/provider, prompt/session/thread, runtime/device, credential/account, persona/presentation, memories, PersonModel, surface/channel/body, or behavioral similarity.

## Problem

If identity is inferred from mutable characteristics or external bindings, replacement of those things can silently replace the companion. If every durable subsystem is embedded in the Person record, `CompanionPerson` becomes a god-object and storage topology becomes identity semantics.

## First principles

```text
Identity is primitive, not inferred.
Continuity ≠ similarity.
Person evolution ≠ Person replacement.
Loss of faculty ≠ loss of Person.
Semantic ownership ≠ physical embedding.
Runtime instance ≠ Person.
State copy ≠ identity continuity.
```

If X is not the Person, replacing X must preserve `PersonID` unless an explicit new-Person creation operation occurs.

## Minimum canonical domain state

```text
CompanionPerson {
    person_id
    created_at
    lifecycle_state  // ACTIVE | ARCHIVED
}
```

Rules:
- `person_id` is immutable and never reassigned;
- `created_at` is immutable historical metadata;
- `lifecycle_state` changes only through explicit Person lifecycle operations;
- schema/version/update metadata belongs to persistence infrastructure, not Person semantics.

Canonical identity invariant:

```text
PersonID ≠ ModelID ≠ SessionID ≠ ThreadID ≠ CredentialID ≠ BodyID
```

## Semantic relations

```text
CompanionPerson
  ├── identity-owns continuity-bearing SelfModel
  ├── participates in RelationshipState
  ├── scopes/participates in canonical InteractionEvents
  ├── holds admitted MemoryClaims / PersonClaims
  └── binds replaceable faculties and interaction contexts
```

These relations do not require reference arrays on the Person record.

### Self

`SelfModel` is canonical continuity-bearing state owned by the Person but distinct from identity itself.

```text
PersonID = which Person this is
SelfModel = durable self-state of that Person
```

Self classes at this gate are:

```text
CONSTITUTIONAL
SLOWLY_MUTABLE
DERIVED_NARRATIVE
```

Freely mutable style, wording, voice/avatar choice, surface adaptation, and presentation state belong to Persona/Presentation rather than `SelfModel`.

`Narrative Self ≠ Autobiographical Evidence`.

Exact Self fields remain Decision 02.

### Relationship

`RelationshipState` is first-class durable relational state. Person participates in it; relationship is not intrinsic Person identity.

```text
new thread ≠ new relationship
model/provider/surface/channel/body change ≠ new relationship
```

Relationship state must not become a catch-all PersonModel, memory bucket, conversation-history container, interaction-policy container, or synthetic relationship/personality score.

Exact F4 relationship fields remain Decision 03.

### Canonical history

Historical truth is represented by canonical `InteractionEvent`s. Person does not require a physically owned Timeline aggregate.

```text
Person Timeline
= ordered historical view of canonical InteractionEvents attributable/scoped to Person
```

One event may also be relationship-, thread-, surface-, or future-work-scoped without duplication. `Timeline` is not a required first-class F4 entity unless a future forcing function gives it independent identity/lifecycle semantics.

Canonical history is append-oriented. Ordinary corrections create new state/events or explicit correction records rather than silently rewriting historical truth. Governed privacy erasure is separate.

`InteractionEvent ≠ EvidenceItem`.

### Memory and claims

Memory is semantic admission state, not a database, vector store, message history, or current context.

```text
history/evidence
      ↓
MemoryAdmissionPolicy
      ↓
MemoryClaim / PersonClaim
```

Person holds admitted claims semantically; claims remain independent canonical records and are not enumerated on the Person record.

Claims distinguish:

```text
HOLDER   who holds/remembers it?
SUBJECT  who/what is it about?
SCOPE    where does it apply?
SOURCE   how is it known and supported?
```

These dimensions are independent. A `PersonClaim` held by Alsoul about a counterpart is Alsoul's admitted interpretation, not canonical state of the counterpart. `PersonModel` remains a rebuildable projection over current claims.

### Replaceable bindings

A binding is a replaceable relation between Person and an external, presentational, interaction, or runtime faculty/context.

```text
BindingID ≠ PersonID
binding replacement → same PersonID
binding absence      → Person remains valid
binding failure      → faculty unavailable, Person unchanged
rebinding            ≠ Person migration
```

Foundation categories include current `ModelBinding` and future `CredentialBinding`, `SurfaceBinding`, `ChannelBinding`, and `EmbodimentBinding`. Device/host location remains infrastructure unless future product semantics require otherwise.

Binding-local state may project canonical Person state but may never become the sole source of Self, Relationship, History, Evidence, Claims, or identity.

```text
credential available
≠ permission
≠ approval
≠ confirmed effect
```

## Creation

A new Person exists only when a new `PersonID` and minimum valid canonical `SelfModel` have been committed.

```text
allocate new PersonID
      +
commit minimum valid SelfModel
      ↓
ACTIVE CompanionPerson
```

Model/provider, credential, relationship, thread, surface, channel, or embodiment availability is not a creation prerequisite. Incomplete persistence is an implementation/recovery condition, not a half-valid Person lifecycle state.

## Lifecycle

Initial lifecycle:

```text
ACTIVE
ARCHIVED
```

Provider unavailable, credential expired, channel offline, binding unbound, runtime degraded, and hydration incomplete are not Person lifecycle values.

```text
ACTIVE
  ↓ explicit archive
ARCHIVED
  ↓ explicit reactivation
ACTIVE   // same PersonID
```

Archival preserves identity and canonical associated state while disabling ordinary runtime participation. Reactivation reconstructs the same Person.

## Reconstruction / hydration

```text
CREATE PERSON
→ new PersonID

HYDRATE / RECONSTRUCT PERSON
→ existing PersonID
→ new runtime representation of same Person
```

Canonical continuity reconstructs before replaceable bindings:

```text
load Person identity/lifecycle
      ↓
load minimum valid SelfModel
      ↓
resolve relevant RelationshipState
      ↓
load continuity-critical valid claims / needed PersonModel projection
      ↓
resolve canonical history head/revision
      ↓
bind available model/provider/capabilities
      ↓
build runtime faculties
      ↓
ONLY THEN permit cognition that depends on those inputs
```

Hydration does not require loading every memory or relationship. Missing required continuity-bearing state must not be silently replaced with defaults and presented as successful continuity.

Valid provider-unavailable state:

```text
Person = available
Self/Relationship/History = available
Cognition binding = unavailable/unbound
```

A new runtime instance never implies a new Person.

## Replacement / copy / migration

These preserve `PersonID`:

```text
replace model/provider
replace persona/presentation
new thread
new surface/channel
replace voice/body
replace runtime/process/device
remove/rebind credential
valid SelfModel revision
relationship evolution
claim correction/supersession
context reset/compaction
```

A genuine new Person requires explicit creation of a new `PersonID`.

Exact state copying does not itself establish identity continuity. A fork intended as a new Person receives a new `PersonID`. Same-Person migration/portability remains a future seam with separate security/authority semantics.

## Erasure boundary

Person erasure is a separately governed data/privacy operation, not a normal lifecycle value.

```text
forget/retract claim
≠ erase InteractionEvent
≠ archive RelationshipState
≠ archive CompanionPerson
≠ erase CompanionPerson
```

Ordinary cognition cannot erase or reassign Person identity. A `PersonID` that once identified one Person must never later identify another Person.

## Required acceptance proofs

```text
replace model/provider
→ same PersonID, SelfModel, Relationship, history, claims

replace persona/presentation
→ same PersonID and SelfModel

remove credential
→ Person/Self/Relationship/history survive
→ cognition becomes unavailable

new thread/surface/channel/runtime/device
→ same PersonID
→ no implicit new RelationshipState

valid SelfModel revision
→ same PersonID

archive then reactivate
→ same PersonID and canonical associated state

explicit fork/clone into new Person
→ new PersonID
```

Recovery proof:

```text
persist canonical Person/Self/Relationship/history/claims
kill process and discard runtime/model context
reconstruct existing PersonID
reconstruct required Self + relevant Relationship + continuity-critical claims
resolve history revision
only then attach available bindings and permit dependent cognition
→ same semantic Person
```

Failure proofs:

```text
required SelfModel missing/corrupt
→ do not silently substitute default Self and claim continuity

provider initialization fails
→ Person still hydrates
→ cognition binding remains unavailable
```

## Consequence

The minimum Person kernel is intentionally small:

```text
CompanionPerson {
    person_id
    created_at
    lifecycle_state
}
```

Rich continuity belongs to canonical associated domains with explicit semantics. This closes F2 Decision 01 without widening F4.