# F4 Implementation Bootstrap

**Status:** Closed executable F4 foundation checkpoint
**Publication:** GitHub-safe

This document records the executable Alsoul foundation slice that began as the first F4 bootstrap and now forms the closed F4 walking-skeleton checkpoint. The implementation remains intentionally narrower than the full semantic architecture.

See [F4 Exit Audit](F4_EXIT_AUDIT.md) for the closure evidence.

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

The executable slice also includes bounded conversational response, exact immediately-prior Timeline context, and relationship-scoped `DECISION` ConversationOpenLoops with deterministic source references and explicit counterpart-authored aliases.

The original acceptance scenario uses one factual personal predicate and one fresh world predicate:

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

F4 is a Python package with a relational persistence layer, migration set, typed command/result objects, semantic application services, deterministic test adapters, configured world/model/presentation boundaries, a local first-party surface, and an executable acceptance suite.

The implementation deliberately uses a file-backed relational database in tests so complete service/runtime object death can be exercised without losing canonical state. The schema remains portable and uses explicit foreign keys, uniqueness fences, immutable records, current heads, append-oriented lifecycle rows, and relationship-local Timeline sequencing.

## Application boundaries

Canonical F4 writes occur through semantic services rather than generic persistence mutation. The implemented boundaries include identity resolution and trusted ingress, memory admission, Investigation/Observation/WorldResult admission, ContextProjection, model invocation, output adoption, presentation, and bounded ConversationOpenLoop lifecycle/selection.

Retries use stable operation identity at database-command boundaries. A new world acquisition creates a new Observation. A new model attempt creates a new ModelInvocation. Output adoption is fenced by one OutputTarget, while first-party text presentation is fenced by one Timeline event per CompanionOutput.

## Recovery

No mutable turn-status aggregate is canonical. The recovery coordinator derives progress from durable rows and resumes from the furthest trustworthy committed stage rather than replaying the whole turn.

Open-loop-aware recovery also revalidates the exact selector semantics pinned into ContextProjection provenance before another provider execution.

## Explicit exclusions after F4 closure

The closed F4 checkpoint does not implement:

- personal digital-world connectors such as calendar, files, messages, contacts, or device state;
- authority enforcement for personal resources through capability/resource/permission/approval layers;
- effectful external Actions or ExecutionAttempt/Effect reconciliation;
- durable delegated Tasks, Commitments, Procedures, Triggers, or WorkRuns;
- proactive WorldSignal-driven behavior;
- rich modality/streaming reception truth or embodiment;
- AffectState or broader PresentationProfile learning;
- broad ConversationOpenLoop kinds, automatic expiry/supersession behavior, semantic alias/reference matching, or generic semantic history retrieval.

These are later-gate concerns and do not keep F4 open.

## Acceptance bar

The suite asserts both final behavior and internal provenance. In particular, it verifies that:

- memory claims require semantically supporting counterpart evidence;
- corrections append rather than overwrite;
- current claim selection is relation-derived;
- a WorldResult cannot borrow evidence from another Investigation;
- provider/session/runtime death does not change Person or Relationship identity;
- ContextProjection carries the exact selected personal/world/conversational sources;
- GeneratedOutput and CompanionOutput do not become shared history before presentation;
- presentation retries produce one canonical Timeline event;
- process recomposition does not duplicate already-durable world/model/presentation work;
- open-loop resume/resolve/cancel remains exact, relationship-scoped, and fail-closed;
- complete runtime reconstruction from durable storage preserves the end-to-end provenance chain.
