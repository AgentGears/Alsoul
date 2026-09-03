# Alsoul Future Work Register

**Document class:** Architecture reservation / deferred-work register  
**Version:** 0.1  
**Prepared:** 2026-09-03  
**Programme:** Alsoul  
**Publication:** GITHUB-SAFE  
**Status:** ACTIVE

---

## 1. Purpose

This register preserves deliberately postponed architecture without turning it into current implementation scope.

Canonical rules:

```text
Postponed ≠ Forgotten
Postponed ≠ Backlog
Reserved ≠ Committed Feature
Deferred ≠ Planned Next
```

The goal is to make future capabilities architecturally possible while paying only the minimum semantic cost today.

Each entry records four things:

```text
INTENT
Why might Alsoul need this?

BOUNDARY
What must today's architecture preserve?

TRIGGER
What real product condition justifies activating it?

PROOF
What must eventually be true for us to call it correct?
```

This file does not authorize implementation by itself.

---

## 2. Status model

### `RESERVED`

The architecture deliberately preserves a seam or non-collapse invariant. The capability itself is not yet planned for implementation.

### `DEFERRED`

The future capability/domain is expected to matter, but its activation condition has not occurred or its prerequisites are not stable.

### `ACTIVATED`

A concrete forcing function exists. Architecture/design work for the item may begin within its target gate.

### `DELIVERED`

The required contract is implemented and verified against the acceptance evidence recorded here or in a superseding contract.

Status progression is not automatic:

```text
RESERVED / DEFERRED
        ↓ activation trigger occurs
review
        ↓ explicit decision
ACTIVATED
        ↓ implementation + verification
DELIVERED
```

---

## 3. Reservation strength

Each item declares the amount of groundwork required now.

### `NONE`
No current architectural accommodation is required beyond general design discipline.

### `BOUNDARY`
Current architecture must preserve semantic/ownership separation, but no interface or schema extension is required yet.

### `EXTENSION_POINT`
Current foundation types/interfaces must remain capable of representing the future contract without identity/source-of-truth migration.

---

## 4. Review policy

Deferred work is reviewed at architectural gate transitions, not continuously.

Default review points:

```text
F2 close
F3 close
F4 user validation
entry into the item's target gate
occurrence of the item's activation trigger
```

Do not assign calendar estimates, sprint dates, or implementation commitments while an item remains `RESERVED` or `DEFERRED`.

---

# Reserved and deferred work

## FW-001 — Resident operational continuity

**Status:** `DEFERRED`  
**Target gate:** F5/F6  
**Reservation strength:** `BOUNDARY`

### Intent

Allow the same `CompanionPerson` to remain operational across longer-lived runtime contexts without making any single process, host, provider, or credential bundle the Person.

### Why postponed

F4 only requires one recoverable runtime capable of reconstructing the Person. Continuous/resident operation adds lifecycle, hosting, authority, failure, and recovery complexity that is not required to prove the first companion experience.

### Preserve now

- `CompanionPerson` identity is independent of process/host identity.
- canonical durable state reconstructs runtime faculties.
- model/provider/credential bindings remain replaceable.
- runtime ownership must not become canonical person ownership.

### Do not implement now

- permanent background daemon semantics;
- multi-host residency;
- remote wake infrastructure;
- autonomous always-on execution.

### Activation trigger

Activate when a committed product experience requires Alsoul to remain available or continue bounded activity when no foreground interaction process is active.

### Prerequisites

- F3 hydration/recovery contract verified;
- authority boundaries exist for unattended operation;
- explicit lifecycle and failure policy.

### Future proof

```text
kill/replace resident runtime
→ same Person reconstructs
→ canonical history/relationship survive
→ unavailable host capability does not become identity loss
```

**Last reviewed:** 2026-09-03

---

## FW-002 — Durable work and delegation

**Status:** `DEFERRED`  
**Target gate:** F7  
**Reservation strength:** `BOUNDARY`

### Intent

Allow work to outlive a temporary executor while the foreground companion remains the same Person.

### Why postponed

F4 requires no background worker or resumable execution. Introducing a general work runtime now would widen the first slice and risk conflating Person, worker, task, run, and obligation.

### Preserve now

```text
Person ≠ Worker
DelegatedTask ≠ WorkRun
WorkRun ≠ Commitment
```

Current foundation objects must not absorb worker/execution identity.

### Do not implement now

- worker orchestration;
- durable run queues;
- retries/resume engines;
- visible specialist personas;
- generic task graphs.

### Activation trigger

Activate when a committed user request must continue beyond one foreground execution or survive worker/process replacement.

### Prerequisites

- stable authority delegation envelope;
- durable state/recovery semantics;
- clear task/run/commitment ownership.

### Future proof

```text
worker dies
→ Person remains present
→ durable work state survives when promised by contract
→ replacement worker cannot inherit undeclared authority
```

**Last reviewed:** 2026-09-03

---

## FW-003 — Skills and reusable procedures

**Status:** `DEFERRED`  
**Target gate:** F7  
**Reservation strength:** `BOUNDARY`

### Intent

Represent reusable learned or authored procedures independently from a single model response or worker implementation.

### Why postponed

No first-slice forcing function requires durable reusable procedures. Premature Skill machinery risks turning transient successful behavior into ungoverned executable policy.

### Preserve now

```text
Memory ≠ Procedure
Procedure ≠ Schedule
Procedure ≠ WorkRun
Procedure ≠ Commitment
```

### Do not implement now

- self-generated executable Skills;
- automatic procedure mutation;
- procedure marketplace;
- generalized workflow authoring.

### Activation trigger

Activate when repeated work benefits materially from a reusable procedure whose meaning must survive model/worker replacement.

### Prerequisites

- work/task semantics;
- authority model for procedure execution;
- versioning/provenance contract.

### Future proof

```text
replace procedure implementation/version
→ historical executions retain provenance
→ Person identity unchanged
→ procedure authority never exceeds current policy
```

**Last reviewed:** 2026-09-03

---

## FW-004 — Cross-mode presence

**Status:** `DEFERRED`  
**Target gate:** F6  
**Reservation strength:** `BOUNDARY`

### Intent

Let one Person appear naturally through multiple interaction modes while preserving relationship and historical continuity.

### Why postponed

F4 is intentionally text-first. Realtime voice/call/ambient presence introduces interruption, latency, modality, and presentation-truth semantics not required for the first proof.

### Preserve now

```text
Person ≠ Thread
Person ≠ Surface
Person ≠ Channel
```

Interaction history must not assume one permanent modality.

### Do not implement now

- voice calling;
- ambient desktop presence;
- multimodal realtime session orchestration;
- modality-specific identity objects.

### Activation trigger

Activate when a non-text interaction surface becomes committed product scope.

### Prerequisites

- stable Person and timeline identity;
- presentation reconciliation contract;
- surface/channel binding semantics.

### Future proof

```text
switch text ↔ voice/call/other surface
→ same Person
→ same relationship
→ surface-specific style may change without identity replacement
```

**Last reviewed:** 2026-09-03

---

## FW-005 — Replaceable embodiment

**Status:** `RESERVED`  
**Target gate:** F6+  
**Reservation strength:** `BOUNDARY`

### Intent

Allow avatar, voice, body, or physical embodiment to change without replacing the Person.

### Why postponed

Embodiment is not required to prove personhood, memory, epistemics, or world access. Building it early would bias the architecture toward presentation before identity is stable.

### Preserve now

```text
Person ≠ Embodiment
PersonID ≠ BodyID
Presentation continuity ≠ Cognitive continuity
```

### Do not implement now

- avatar runtime;
- robot/body control;
- body-specific memory ownership;
- embodiment-specific Person identity.

### Activation trigger

Activate when an avatar, voice identity, animated body, or physical body becomes a committed interaction experience.

### Prerequisites

- cross-mode identity continuity;
- `EmbodimentBinding` semantics;
- authority model for effectful bodies where relevant.

### Future proof

```text
replace body/avatar/voice
→ same PersonID
→ same relationship/history
→ embodiment-specific state does not become Person identity
```

**Last reviewed:** 2026-09-03

---

## FW-006 — Portable Person

**Status:** `DEFERRED`  
**Target gate:** Post-F5  
**Reservation strength:** `BOUNDARY`

### Intent

Move or reconstruct the same Person across independent environments without silently moving authority.

### Why postponed

Safe portability requires mature identity, recovery, credentials, authority, migration, and conflict semantics. A broad application backup is not sufficient proof of Person continuity.

### Preserve now

```text
Person identity ≠ Credential
Person state ≠ Application state
Person portability ≠ Authority portability
```

Credentials and environmental authority remain explicit bindings.

### Do not implement now

- export/import Person bundles;
- automatic credential migration;
- cross-device conflict resolution;
- remote cloning semantics.

### Activation trigger

Activate when the same Person must move between independent devices/runtimes or survive replacement of the current operational home.

### Prerequisites

- verified hydration/recovery package;
- explicit credential rebinding;
- authority portability policy;
- canonical-state version/migration semantics.

### Future proof

```text
move Person state
→ same Person identity/history/relationship reconstruct
→ credentials and authority do not appear unless explicitly rebound
```

**Last reviewed:** 2026-09-03

---

## FW-007 — Durable commitments

**Status:** `DEFERRED`  
**Target gate:** F7  
**Reservation strength:** `BOUNDARY`

### Intent

Allow Alsoul to form user-facing obligations whose meaning survives task, worker, process, and execution-strategy replacement.

### Why postponed

Commitment semantics create user reliance. They should not be introduced until Alsoul can reliably persist, execute, recover, and report long-horizon work.

### Preserve now

```text
ConversationOpenLoop ≠ DelegatedTask
DelegatedTask ≠ WorkRun
WorkRun ≠ Commitment
```

Product language must not create durable reliance before the underlying contract exists.

### Do not implement now

- generic commitment engine;
- broad proactive promises;
- recurring obligation scheduler;
- automatic conversion of tasks/reminders into commitments.

### Activation trigger

Activate when Alsoul is expected to say the equivalent of "I'll make sure", "I'll keep an eye on this", or otherwise create durable user reliance beyond the current interaction.

### Prerequisites

- durable work/recovery;
- scheduling where relevant;
- authority and effect truth;
- explicit acceptance/completion semantics.

### Future proof

```text
replace worker/procedure/process
→ obligation remains
→ completion requires acceptance evidence
→ run completion alone cannot prove commitment fulfillment
```

**Last reviewed:** 2026-09-03

---

## FW-008 — Governed procedural learning

**Status:** `DEFERRED`  
**Target gate:** F7+  
**Reservation strength:** `BOUNDARY`

### Intent

Allow Alsoul to improve reusable procedures from experience without silently rewriting authority, identity, or executable policy.

### Why postponed

Self-modifying procedures combine learning with operational authority and require stronger governance than ordinary memory adaptation.

### Preserve now

```text
Memory adaptation
≠ Relationship learning
≠ Procedural learning
≠ Self-constitution change
```

### Do not implement now

- autonomous Skill rewriting;
- automatic executable-policy mutation;
- self-constitutional changes triggered by task outcomes.

### Activation trigger

Activate when repeated experience should modify a reusable procedure rather than merely add memory or relationship understanding.

### Prerequisites

- versioned procedures;
- evaluation criteria;
- proposal/review/admission semantics;
- authority constraints for learned procedures.

### Future proof

```text
experience proposes procedure change
→ old procedure remains attributable
→ change is governed/versioned
→ new procedure cannot broaden authority by learning
```

**Last reviewed:** 2026-09-03

---

## FW-009 — Cryptographic Person principal

**Status:** `RESERVED`  
**Target gate:** Future federation / multi-domain identity  
**Reservation strength:** `BOUNDARY`

### Intent

Allow the Person to prove authorship/identity across independent trust domains without defining the Person as a cryptographic key.

### Why postponed

The first foundation requires local durable identity, not federated or independently verifiable social identity. Cryptographic identity would add key lifecycle, recovery, rotation, delegation, and compromise semantics before a forcing function exists.

### Preserve now

```text
Person ≠ Principal
PersonID ≠ KeyID
Identity continuity ≠ Credential continuity
```

### Do not implement now

- signing identity;
- decentralized/federated principal infrastructure;
- key-based personhood;
- cross-domain delegation chains.

### Activation trigger

Activate when Alsoul must prove authorship/identity to an external trust domain independently of the current application/provider account.

### Prerequisites

- stable Person identity/recovery;
- key rotation/recovery model;
- authority delegation semantics.

### Future proof

```text
rotate/recover cryptographic key
→ same Person
→ historical authorship remains verifiable under defined migration semantics
```

**Last reviewed:** 2026-09-03

---

## FW-010 — Personal-world authority

**Status:** `DEFERRED`  
**Target gate:** F5  
**Reservation strength:** `EXTENSION_POINT`

### Intent

Let Alsoul read selected personal-world resources and later perform bounded external actions under explicit authority.

### Why postponed

F4 proves only read-only public-world observation. Personal data and mutation introduce privacy, credential, permission, approval, resource-scope, and effect-certainty obligations.

### Preserve now

The World Interface must remain compatible with typed capabilities and scoped observations. F4 read access must not imply future write authority.

Canonical boundary:

```text
Host Capability
  ∩ AI Capability Policy
  ∩ Resource Scope
  ∩ Permission
  ∩ Per-Action Approval
  → Attempted Effect
  → Confirmed | Failed | Uncertain
```

### Do not implement now

- personal file/calendar/email connectors;
- write/mutation authority;
- broad always-allow permissions;
- ambient credential transfer.

### Activation trigger

Activate when a committed user experience requires reading private/personal resources or performing an external effect.

### Prerequisites

- capability metadata contract;
- credential binding store;
- permission/approval semantics;
- effect receipts and uncertain-effect reconciliation.

### Future proof

```text
capability installed
≠ authorized

permission granted
≠ effect confirmed

ambiguous non-idempotent effect
→ UNCERTAIN_EFFECT
→ no blind replay
```

**Last reviewed:** 2026-09-03

---

## FW-011 — Presentation reconciliation

**Status:** `DEFERRED`  
**Target gate:** F6  
**Reservation strength:** `EXTENSION_POINT`

### Intent

Preserve shared historical truth about what the user actually received when output delivery can be interrupted or partial.

### Why postponed

F4 text interaction can initially treat persisted delivered text as the shared transcript. Realtime speech, streaming presentation, cancellation, and interruption require stronger delivery semantics.

### Preserve now

`InteractionEvent` must remain extensible enough to associate future presentation/delivery state without rewriting Person identity or canonical source events.

```text
Generated Output
≠ Presented Output
≠ Experienced / Heard Output
```

### Do not implement now

- token/audio delivery receipts;
- TTS word-level history reconciliation;
- realtime duplex arbitration;
- modality-specific receipt stores.

### Activation trigger

Activate when Alsoul produces realtime or interruptible output for which generated content may differ materially from what the user receives.

### Prerequisites

- surface/channel contract;
- realtime lifecycle/cancellation semantics;
- explicit definition of what counts as presented/experienced for each modality.

### Future proof

```text
generate full response
→ user receives only prefix
→ later shared history cannot treat unheard/unseen suffix as experienced conversation
```

**Last reviewed:** 2026-09-03

---

# 5. Current architectural reservations summary

| ID | Area | Status | Target | Preserve now |
|---|---|---|---|---|
| FW-001 | Resident operational continuity | DEFERRED | F5/F6 | runtime/host ≠ Person |
| FW-002 | Durable work/delegation | DEFERRED | F7 | Person ≠ Worker; Task ≠ Run ≠ Commitment |
| FW-003 | Skills/procedures | DEFERRED | F7 | Memory ≠ Procedure; Procedure ≠ Run |
| FW-004 | Cross-mode presence | DEFERRED | F6 | Person ≠ Surface ≠ Channel |
| FW-005 | Replaceable embodiment | RESERVED | F6+ | Person ≠ Embodiment |
| FW-006 | Portable Person | DEFERRED | Post-F5 | Person portability ≠ authority portability |
| FW-007 | Durable commitments | DEFERRED | F7 | Task/Run ≠ Commitment |
| FW-008 | Governed procedural learning | DEFERRED | F7+ | memory/relationship/procedure/self learning separate |
| FW-009 | Cryptographic Person principal | RESERVED | Future | Person ≠ Principal/Key |
| FW-010 | Personal-world authority | DEFERRED | F5 | capability/permission/approval/effect separate |
| FW-011 | Presentation reconciliation | DEFERRED | F6 | generated/presented/experienced separate |

---

# 6. Activation decision template

When an activation trigger occurs, record a project-native decision before implementation:

```yaml
future_work_id: FW-XXX
decision: activate | remain-deferred | retire | supersede
forcing_function: <concrete Alsoul product requirement>
target_gate: <gate>
prerequisites_met:
  - <item>
scope_authorized: <exact bounded scope>
acceptance_contract: <tests/proof required>
decision_date: YYYY-MM-DD
```

Activation authorizes architecture/design work only within the stated scope. It does not automatically authorize every capability implied by the future domain.

---

# 7. Standing rule

When current architecture touches a deferred domain:

1. preserve the declared boundary/extension point;
2. do not build the deferred subsystem merely because the seam exists;
3. update this register if the current decision changes the future contract;
4. activate only when the recorded product forcing function exists.

The intended discipline is:

> **Stay narrow now while leaving a precise, testable path for future Alsoul.**
