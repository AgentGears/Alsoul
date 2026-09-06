# F4 Implementation Bootstrap

**Status:** Initial executable foundation
**Publication:** GitHub-safe

This document records the first concrete implementation slice of the Alsoul foundation. The implementation is intentionally narrower than the full semantic architecture.

## Scope

The implemented F4 path proves:

```text
CompanionPerson / Self
↓
CounterpartPerson / RelationshipState
↓
canonical Timeline
↓
evidence-grounded factual memory
↓
complete runtime death and hydration
↓
fresh Investigation / Observation / WorldSourceCapture
↓
evidence-backed WorldResult
↓
immutable ContextProjection
↓
ModelInvocation / GeneratedOutput
↓
CompanionOutput adoption
↓
canonical presented Timeline event
```

The first acceptance scenario uses one factual personal predicate and one fresh world predicate:

```text
personal:
    primary_machine.memory_gb

world:
    software.minimum_memory_gb
```

The final response contract separates:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

so the host can mechanically validate the meaning behind `You told me...`, `I checked...`, and `My take...` before adoption.

## Concrete stack

The bootstrap is a Python package with a relational persistence layer, migration set, typed command/result objects, semantic application services, deterministic test adapters, and an executable acceptance suite.

The implementation deliberately uses a file-backed relational database in tests so complete service/runtime object death can be exercised without losing canonical state. The schema remains portable and uses explicit foreign keys, uniqueness fences, immutable records, current heads, and relationship-local Timeline sequencing.

## Application boundaries

Canonical F4 writes occur through semantic services rather than generic persistence mutation:

```text
ResolveInboundIdentity
AppendCounterpartInput
AdmitPersonMemoryClaim
StartInvestigation
StartObservation
RecordObservationSuccess / Failure
AdmitWorldResult
BuildContextProjection
StartModelInvocation
CompleteModelInvocation
ResolveOutputTarget
AdoptCompanionOutput
PresentCompanionOutput
```

Retries use stable operation identity at database-command boundaries. A new world acquisition creates a new Observation. A new model attempt creates a new ModelInvocation. Output adoption is fenced by one OutputTarget, while first-party text presentation is fenced by one Timeline event per CompanionOutput.

## Recovery

No mutable turn-status aggregate is canonical. The recovery coordinator derives progress from durable rows:

```text
INPUT_ADMITTED
PROJECTION_READY
GENERATED
ADOPTED
PRESENTED
```

A restart therefore resumes from the furthest trustworthy committed stage instead of replaying the whole turn.

## Explicit exclusions

The bootstrap does not implement effectful external Actions, durable delegated Tasks, proactive WorldSignals/Triggers, rich modality/streaming, AffectState, PresentationProfile learning, or ConversationOpenLoop lifecycle. Their architecture remains separate from the F4 persistence tables.

## Acceptance bar

The suite asserts both final behavior and internal provenance. In particular, it verifies that:

- memory claims require semantically supporting counterpart evidence;
- corrections append rather than overwrite;
- current claim selection is relation-derived;
- a WorldResult cannot borrow evidence from another Investigation;
- provider/session death does not change Person or Relationship identity;
- ContextProjection carries the selected personal/world sources;
- GeneratedOutput and CompanionOutput do not become shared history before presentation;
- presentation retries produce one canonical Timeline event;
- complete runtime reconstruction from durable storage preserves the end-to-end provenance chain.
