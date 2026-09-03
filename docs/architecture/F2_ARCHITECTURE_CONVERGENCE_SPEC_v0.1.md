# Alsoul F2 Architecture Convergence Specification

**Document class:** Architecture convergence specification  
**Specification version:** 0.1  
**Prepared:** 2026-09-03  
**Programme:** Alsoul  
**Gate:** F2 — Architecture Convergence  
**Status:** Working specification; intended to close F2 before F3 implementation  
**Upstream basis:** Alsoul Foundation Roadmap v0.6 and Architecture Pattern Register v0.6

---

## 1. Purpose

This specification converts the accumulated Alsoul research vocabulary into the **smallest exact architecture** needed to make the product constitution and user-experience contracts difficult to violate accidentally.

It is not an implementation plan and does not authorize F3/F4 by itself.

> **Alsoul is a persistent personal companion situated in the user's world, capable of remembering, perceiving, investigating, acting, and interpreting without pretending that external information is knowledge it inherently possesses.**

Experiential north star:

> **Alsoul should feel like someone who knows you, lives in your world, and knows the limits of what they know and can do.**

Canonical simplification:

> **Complex architecture → simple person.**

---

## 2. F2 closure rule

F2 closes when:

1. every foundational semantic responsibility has one canonical owner;
2. canonical durable state is distinguishable from derived projections and runtime state;
3. replacement/recovery behavior is specified for each foundational object;
4. epistemic source and admissible use are explicit enough to prevent source collapse;
5. memory and PersonModel claims retain sufficient evidence to be revisable;
6. world access produces evidence/results rather than silent prompt truth;
7. future authority/work/presence concepts have stable seams without being pulled into F4;
8. user-experience contracts map to concrete architecture invariants;
9. the F4 minimum subset is unambiguous;
10. remaining questions are bounded and do not threaten the first vertical slice.

---

## 3. State classes

The foundation uses four state classes:

```text
CANONICAL DURABLE STATE
  facts/events/claims whose persistence defines continuity

DERIVED DURABLE STATE
  rebuildable interpretations or indexes persisted for efficiency

RUNTIME STATE
  hydrated operational objects used by the current process

PROJECTION STATE
  bounded views built for a model, surface, or task
```

A projection must never silently become canonical truth.

Canonical direction:

```text
                      CompanionPerson
                            │
                ┌───────────┼───────────┐
                │           │           │
             Self       Relationship   Bindings
                │           │
                │      Counterpart Model
                │           │
                └──────┬────┘
                       │
              Timeline / Evidence
                       │
                 Memory / Claims
                       │
               Epistemic Controller
                       │
        ┌──────────────┴──────────────┐
        │                             │
 ContextProjection               World Interface
                                      │
                                 Observation
                                      │
                                  WorldResult
                                      │
                                Interpretation
```

Future seams beneath the same Person:

```text
Capability / Authority
Work / Delegation
Surface / Channel / Embodiment
```

---

## 4. Foundation-required first-class objects

### 4.1 `CompanionPerson`

Canonical identity root of the artificial companion.

Owns/references:
- `SelfModel`
- counterpart `RelationshipState`
- canonical timeline identity
- durable claim/person-model references
- replaceable cognition/surface/channel/embodiment bindings

Must not derive identity from:
- current LLM/provider
- prompt/session/thread
- worker/device
- avatar/voice
- credentials

```text
PersonID ≠ ModelID ≠ SessionID ≠ ThreadID ≠ CredentialID ≠ BodyID
```

### 4.2 `InteractionEvent`

Canonical historical interaction truth. The timeline is append-oriented; corrections and supersession are new state/events rather than silent destructive rewrites.

### 4.3 `EvidenceItem`

Canonical recoverable support for a claim or interpretation.

Minimum semantics:

```text
evidence_id
kind
source_kind
source_ref
observed_or_recorded_at
validity/freshness when relevant
scope/privacy
content or stable content reference
```

Evidence may point to an InteractionEvent, Observation, WorldResult, artifact, or other source record.

### 4.4 `MemoryClaim`

Durable admitted/derived remembered claim.

Minimum semantics:

```text
claim_id
assertion
source/admission kind
status
evidence links
validity metadata
supersession/contradiction relation when relevant
```

### 4.5 `PersonClaim`

**F2 decision:** a semantic specialization of `MemoryClaim` in the first implementation; it need not start as a separate storage table.

Additional semantics:

```text
subject person
interpretation kind
confidence/strength when derived
support requirement
counterevidence/alternative hooks
```

A PersonClaim is a model of a person, not the person.

### 4.6 `RelationshipState`

Current durable relationship state between Alsoul and a counterpart. It must not become a catch-all user profile or synthetic personality score.

### 4.7 `SelfModel`

Durable self-state owned by `CompanionPerson`, partitioned into:

```text
CONSTITUTIONAL
SLOWLY_MUTABLE
FREELY_MUTABLE / PRESENTATIONAL
DERIVED_NARRATIVE
```

`Narrative Self ≠ Autobiographical Evidence` remains mandatory.

### 4.8 `Observation`

Typed acquisition from outside the Person.

Minimum semantics:

```text
observation_id
observer/capability
source
observed_at
freshness/validity
payload reference
scope/privacy
```

`Observation ≠ MemoryClaim`.

### 4.9 `WorldResult`

Evidence-bearing result of world access/investigation.

Minimum semantics:

```text
result_id
observation/evidence links
source/freshness
canonical payload
optional derived summary/projection
```

`WorldResult ≠ Companion Interpretation`.

### 4.10 `ContextProjection`

Bounded rebuildable projection for a model invocation or cognitive task. It may contain selected history, claims, PersonModel projection, observations, compressed world/tool results, and current temporal/runtime context.

It must retain enough source revision information to reject stale derivations where material.

`ContextProjection` is never canonical historical truth.

---

## 5. Required semantic components that may initially be embedded

### `PersonModel / CounterpartPersonModel`

A derived view over current `PersonClaim`s and relationship-relevant interpretation. The underlying evidence + claims are canonical; the PersonModel projection is not.

### `Persona / Presentation Profile`

Replaceable interaction/presentation configuration beneath `CompanionPerson`. It may hold style/prompt fragments, surface defaults, voice/avatar preferences, and interaction settings, but it cannot own Person identity.

### `AffectState`

May be persisted if continuity requires it, but F2 does not require a rich emotion ontology. Transient affect must remain distinct from stable traits.

### `Investigation`

A one-shot F4 lookup may remain ephemeral. A durable Investigation becomes necessary only when multiple observations, asynchronous continuation, delegation, cancellation, or inspectability require it.

### `WorldSignal / Trigger`

May initially be an event envelope rather than a durable entity.

```text
Signal that information exists ≠ Observation of the information
```

---

## 6. Future seams — defined but not required for F4

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

Earlier foundation objects must not absorb these responsibilities merely because their implementations are deferred.

---

## 7. Ownership/source-of-truth matrix

| Concept | Canonical owner/source | Durable | Rebuildable | F4 |
|---|---|---:|---:|---:|
| Companion identity | `CompanionPerson` | Yes | No | Yes |
| Self constitution | `SelfModel` | Yes | No | Minimal |
| Relationship | `RelationshipState` | Yes | No | Minimal |
| Interaction history | `InteractionEvent` timeline | Yes | No | Yes |
| Load-bearing evidence | `EvidenceItem` / source record | Yes | No | Yes |
| Memory claim | `MemoryClaim` | Yes | Current view only | Yes |
| Person understanding | `PersonClaim`s | Yes | PersonModel view yes | Minimal |
| PersonModel | derived from claims | Optional | Yes | Minimal |
| Observation | World Interface | policy-dependent | No if retained as history | Yes |
| World result | World Interface | Yes for F4 result | summary yes | Yes |
| Current model context | `ContextProjection` | cache only | Yes | Yes |
| Vector/index representation | index subsystem | Optional | Yes | No semantic dependency |
| Persona/presentation | binding/config | Yes | Replaceable | Minimal |
| Current model/provider | `ModelBinding` | binding | Replaceable | Yes |
| Credentials | credential store/binding | separate | Rebind | adapter-dependent |
| Worker | runtime | No | Replaceable | No |
| Work/task/run | work runtime | Future | Depends | No |
| Surface/channel/body | bindings | Future | Replaceable | No |

---

## 8. Projection rules

### History

```text
InteractionEvent timeline
        ↓
ContextProjection
        ↓
model call
```

Compaction, hiding, summarization, truncation, or context reset may change the projection but cannot delete canonical history merely to satisfy a context window.

### World results

```text
canonical WorldResult
       ├── full result/evidence
       └── derived summary/compression
                 ↓
          ContextProjection
```

A compressed result cannot replace the canonical result.

### Person understanding

```text
EvidenceItem[]
     ↓
PersonClaim[]
     ↓
PersonModel projection
     ↓
ContextProjection / interaction policy
```

The projection may change without rewriting evidence.

---

## 9. Epistemic source model

Minimum F3 source kinds:

```text
SELF
MEMORY
INFERENCE
OBSERVATION
SEARCH_RESULT
TOOL_RESULT
OTHER_PERSON
```

These are epistemic kinds, not storage scopes.

| Source | Factual use | Direct durable memory | PersonClaim use | Freshness |
|---|---|---|---|---|
| SELF | self-state | governed | not external-person evidence | low |
| MEMORY | subject to claim validity | already admitted | yes if underlying evidence supports | claim-dependent |
| INFERENCE | qualified as inference | not without admission | yes, evidence-bound | evidence-dependent |
| OBSERVATION | observation semantics | not automatically | yes if admitted/supported | often |
| SEARCH_RESULT | found/current evidence | not automatically personal memory | only if relevant/admitted | yes |
| TOOL_RESULT | result semantics | not automatically | possible with admission | often |
| OTHER_PERSON | attributed to speaker | not automatically as truth | attributed claims | source-dependent |

Mandatory rule:

```text
Alsoul previously said X
→ evidence that Alsoul said X
≠ evidence that external-world X is true
```

---

## 10. Claim/evidence decisions

### Evidence cardinality

**F2 decision:** claims support one or more evidence links from day one.

```text
Claim ↔ Evidence[]
```

A schema may optimize for a primary evidence link, but the semantic model remains many-to-many.

### Minimum claim status

```text
ACTIVE
SUPERSEDED
RETRACTED
EXPIRED
```

`PROVISIONAL` may be added for derived PersonClaims if useful.

### Correction

```text
old evidence
  ↓
old claim ACTIVE
  ↓ new evidence/correction
old claim SUPERSEDED
new claim ACTIVE
```

Historical evidence remains; current understanding changes.

### Support validation

`Evidence attached to claim ≠ evidence supporting claim`.

F3 must include a claim-specific support-validation path for load-bearing derived claims.

---

## 11. Memory admission contract

All durable memory write paths converge on one semantic boundary.

Possible outputs:

```text
REJECT
ADMIT_AS_EVIDENCE_ONLY
ADMIT_MEMORY_CLAIM
ADMIT_PERSON_CLAIM
```

Minimum rules:

1. world observations do not automatically become autobiographical memory;
2. AI-generated text does not become external fact merely because it appears in history;
3. inferred PersonClaims require supporting evidence;
4. memory scope/privacy is explicit;
5. correction/supersession is supported;
6. extensions/background paths cannot bypass admission.

---

## 12. Hydration/reconstruction contract

```text
DurablePersonState
       ↓
load identity
       ↓
load self + relationship
       ↓
load valid claims / build PersonModel projection
       ↓
load timeline head/revision
       ↓
bind available model/provider/capabilities
       ↓
build runtime faculties
       ↓
ONLY THEN permit new cognition
```

Before the first model call after complete process death, the runtime must know at least:
- `PersonID`
- minimum current `SelfModel`
- `RelationshipState`
- current valid PersonClaims needed for continuity
- canonical timeline head/revision
- current binding state, including unavailable model/credentials

A UI showing persisted relationship state while cognition starts from defaults is a continuity failure.

Provider-unavailable state is:

```text
Person = available
Relationship/history = available
Cognition binding = unavailable/unbound
```

not Person deletion.

---

## 13. ContextProjection contract

A projection should identify:

```text
projection_id
purpose/model/surface
source revisions
selected timeline events
selected memory/person claims
current world/runtime observations
compressed projections when used
generated_at
```

It may be discarded at any time.

### Stale derivation rule

```text
derivation starts at revision R1
source becomes R2
R1 result returns
→ reject / rebase / recompute
```

Applies to memory extraction, PersonClaim derivation, summarization, context compression, and consolidation.

---

## 14. F4 World Interface contract

F4 requires only a **read-only public-world adapter**.

```text
need current/external fact
      ↓
Epistemic Controller chooses world access
      ↓
Observation / search request
      ↓
WorldResult + EvidenceItem(s)
      ↓
result presentation
      ↓
Alsoul interpretation using remembered/person context
```

Minimum `Observation`:

```text
observation_id
kind
source
observed_at
freshness_class
scope
payload_ref / normalized content
```

Minimum `WorldResult`:

```text
result_id
question/request
observation_ids[]
evidence_ids[]
canonical payload
source/freshness metadata
```

One-shot search does not require a durable Investigation object.

---

## 15. User-experience contracts → architecture

| Experience | Architectural proof |
|---|---|
| Same Alsoul after model change | Person independent of `ModelBinding` |
| New chat, same relationship | relationship is Person-scoped, not thread-scoped |
| "I remember..." is truthful | admitted memory/history source exists |
| "I think..." is qualified | inference/PersonClaim distinguished from stated fact |
| "I checked..." is truthful | real Observation/WorldResult exists |
| "What I found" vs "My take" | result/evidence separate from interpretation |
| Correction changes behavior | supersession + projection rebuild |
| Restart feels continuous | hydration before cognition |
| Provider outage ≠ identity loss | Person survives unavailable binding |
| "Why do you think that?" | PersonClaim → supporting EvidenceItems |
| Search freshness is honest | `observed_at` + freshness policy |
| Context trimming ≠ amnesia | canonical timeline independent from projection |

---

## 16. Authority seam — semantic freeze, implementation later

F2 freezes:

```text
Host Capability
      ∩
AI Capability Policy
      ∩
Resource Scope
      ∩
Permission
      ∩
Per-Action Approval
      ↓
Attempted Effect
      ↓
Confirmed | Failed | Uncertain
```

Rules:
- tool availability ≠ authority;
- sandbox/isolation ≠ authorization;
- code authenticity ≠ action authorization;
- approvals are user-intent/resource/effect based, not tool-name based;
- unreadable authority config fails closed;
- a conversational claim does not certify an external effect;
- credentials are bindings, not Person identity.

F4 public search may use a deliberately restricted read-only path without implementing the full F5 authority system.

---

## 17. Work seam — semantic freeze, implementation later

```text
ConversationOpenLoop
≠ DelegatedTask
≠ WorkRun / ExecutionAttempt
≠ Skill / Procedure
≠ Commitment
```

and:

```text
Procedure Definition Durability
≠ Schedule Durability
≠ Execution Durability
≠ Commitment Durability
```

No generic Commitment engine belongs in F4.

---

## 18. Presence seam — semantic freeze, implementation later

Identity remains above SurfaceBinding, ChannelBinding, and EmbodimentBinding.

Future realtime truth preserves:

```text
Generated Output
≠ Presented Output
≠ Heard/Experienced Output
```

F4 text interaction does not need a presentation-receipt subsystem, but the event model must not make later delivery semantics impossible.

---

## 19. F4 minimum subset

Required:

```text
CompanionPerson
SelfModel (minimal)
RelationshipState (minimal)
InteractionEvent timeline
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

Explicitly excluded:

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

## 20. F3 interface targets

F3 should encode at minimum:

```text
PersonRepository
TimelineRepository
EvidenceRepository
ClaimRepository
MemoryAdmissionPolicy
PersonModelProjector
EpistemicPolicy
ContextProjector
WorldInterface
SearchAdapter
Hydrator / PersonRuntimeFactory
```

Language/framework selection is intentionally outside F2.

---

## 21. Mandatory F3 acceptance tests

### Identity

```text
replace model/provider
→ same PersonID and relationship/history
```

```text
replace persona/presentation
→ same PersonID
```

```text
remove provider credential
→ Person/Relationship survive
→ cognition becomes unbound
```

### Recovery

```text
persist state
kill entire process
clear model context
hydrate durable state
→ self/relationship/person claims exist before first model call
```

### History/projection

```text
reset/compact context
→ canonical timeline unchanged
```

```text
hide history from automatic context
→ authorized explicit retrieval still finds it
```

### Memory/PersonModel

```text
admit PersonClaim
→ supporting EvidenceItem(s) recoverable
```

```text
attach irrelevant nearby evidence
→ claim cannot count as grounded
```

```text
user corrects claim
→ old claim superseded
→ history/evidence retained
→ current PersonModel changes
```

```text
AI-generated statement re-enters memory pipeline
→ cannot become external fact solely because Alsoul said it
```

### World

```text
current fact requested
→ world access occurs
→ WorldResult records source/freshness
```

```text
WorldResult exists
→ companion interpretation can be regenerated independently
```

```text
stale observation under policy
→ re-observation occurs
```

### Stale derivation

```text
derivation starts at R1
source changes to R2
→ R1 derivation cannot silently commit as current
```

---

## 22. Explicit F2 decisions in v0.1

Unless challenged by a concrete contradiction:

1. `CompanionPerson` is the identity root.
2. model/provider/persona/thread/surface/body are bindings or contexts, not identity.
3. canonical timeline/history is separate from model context.
4. `EvidenceItem` is first-class when evidence is load-bearing.
5. `PersonClaim` is semantically distinct but may share storage with `MemoryClaim` initially.
6. claims support one-or-more evidence links from day one.
7. `PersonModel` is a projection over claims, not source of truth.
8. memory admission is centralized semantically.
9. epistemic source is separate from memory scope/visibility.
10. source kind constrains admissible use.
11. `Observation`/`WorldResult` mediate external information.
12. simple F4 search does not require a durable Investigation.
13. `ContextProjection` is rebuildable/discardable.
14. runtime continuity requires hydration before cognition.
15. unavailable provider/credential does not invalidate the Person.
16. authority, work, and presence seams are frozen semantically but mostly deferred from F4.
17. F4 remains read-only public-world access.
18. no APR-027 is required to close this architecture.

---

## 23. Remaining F2 decisions

Close these before declaring F2 complete:

1. minimum fields/mutation rules for `CompanionPerson`;
2. constitutional vs slowly mutable SelfModel fields;
3. minimum RelationshipState for F4;
4. first-slice PersonClaim kind vocabulary;
5. support-validation policy for inferred PersonClaims;
6. memory-admission categories/default retention;
7. F4 freshness vocabulary/classes;
8. ContextProjection source-revision representation;
9. recovery package/repository boundaries;
10. user-facing memory correction/inspection semantics required by F3;
11. whether F4 affect is entirely runtime or minimally durable;
12. the precise boundary between InteractionEvent content and separately retained EvidenceItems.

None of these may expand F4 beyond the current walking skeleton.

---

## 24. Next artifact

After these decisions close, produce:

> **Alsoul Foundation Contract + Test Harness Specification (F3) v0.1**

That document should choose concrete interfaces/schemas and executable fixtures. Only after the contract is executable should F4 implementation begin.

---

## 25. Decision summary

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

Everything else is a binding, runtime faculty, derived projection, or future seam.

The remaining F2 work is to finish the **exact ownership and lifecycle contract**, not to discover more categories.
