# F4 End-to-End Runtime Coordinator

## Purpose

This checkpoint composes the existing F4 semantic services into one restart-safe reactive runtime path.

The coordinator does not introduce a mutable turn-status aggregate. It derives what already exists, resumes from the furthest durable semantic boundary, and invokes only the next required operation.

```text
Counterpart input
→ Investigation
→ Observation
→ WorldSourceCapture
→ EvidenceItem
→ WorldResult
→ ContextProjection
→ ModelInvocation
→ GeneratedOutput
→ CompanionOutput
→ presented Timeline event
```

The governing rule is:

> Runtime orchestration may coordinate canonical state transitions, but it may not become a second source of truth about those transitions.

## FoundationResponseCoordinator

`FoundationResponseCoordinator` owns the F4 reactive orchestration path for one already-admitted counterpart input.

Its inputs identify:

```text
Relationship
current input InteractionEvent
presentation SurfaceBinding
presentation ChannelBinding
world acquisition adapter
model provider adapter
```

It does not accept a provider transcript, model session, or reconstructed conversation state.

The coordinator first asks the durable recovery layer what semantic stage already exists.

```text
PRESENTED
→ return the existing presentation

ADOPTED
→ present the existing CompanionOutput

GENERATED
→ adopt the existing GeneratedOutput

PROJECTION_READY
→ execute a new model attempt if allowed

INPUT_ADMITTED
→ recover/acquire world evidence
→ admit WorldResult
→ build ContextProjection
```

An unresolved provider attempt remains a blocker:

```text
MODEL_ATTEMPT_UNRESOLVED
≠ permission to dispatch again
```

A known process-loss invocation must use the explicit provider-reconciliation boundary before retry.

## No persisted turn status

The coordinator does not add:

```text
response.status
turn.status
runtime_step
```

as canonical state.

Progress is derived from the existing domain objects.

```text
WorldResult exists
→ world derivation already committed

ContextProjection exists and remains reusable
→ cognition snapshot already committed

GeneratedOutput exists
→ provider result already committed

CompanionOutput exists
→ adoption already committed

COMPANION_PRESENTED_OUTPUT exists
→ presentation already committed
```

This prevents a mutable orchestration flag from disagreeing with the semantic records it is intended to summarize.

## Recovering the pre-projection world path

The provider-recovery checkpoint already covered `ContextProjection` and later stages. End-to-end recovery also needs an exact way to resume before projection.

For the F4 vertical slice, one logical Investigation belongs to one current input response operation.

The coordinator uses a deterministic application-operation identity for:

```text
StartInvestigation(current_input)
```

This is an idempotency mechanism, not a new product-domain identity. The durable `Investigation` remains the semantic object.

On restart the same operation resolves to the already-created Investigation.

Within that Investigation:

```text
admitted WorldResult exists
→ reuse it

no WorldResult
+ successful Observation/Capture/Evidence exists
→ derive and admit WorldResult from that capture

no successful capture
+ known process loss
→ create a new Observation and reacquire

no successful capture
+ STARTED Observation
+ no known process loss
→ block as unresolved
```

A retry never overwrites the previous Observation.

## Durable provider-dispatch checkpoints

Both provider runners now expose an optional hook immediately after their attempt record is durably committed and before provider dispatch.

World acquisition:

```text
Observation(STARTED)
→ checkpoint
→ provider acquisition
```

Model generation:

```text
ModelInvocation(IN_PROGRESS)
→ checkpoint
→ provider generation
```

The checkpoint is outside the provider exception handler.

Therefore simulated or real process loss at that boundary preserves:

```text
Observation = STARTED
ModelInvocation = IN_PROGRESS
```

instead of falsely rewriting either attempt as a definite failure.

These hooks are orchestration/testing hooks. They do not create Timeline or epistemic state.

## Process-loss reconciliation

After a known runtime loss, provider recovery now reconciles every orphaned `IN_PROGRESS` model attempt belonging to the reactive response, including attempts attached to a ContextProjection that has since become stale.

This distinction matters:

```text
projection stale
≠ provider attempt definitely completed
```

Staleness controls whether a projection may be reused. It does not change what happened to an abandoned provider attempt.

A known lost owner permits:

```text
IN_PROGRESS
→ UNKNOWN
```

but does not dispatch another request.

## Current-input frontier

A new F4 response may begin only when the current counterpart input is the relationship Timeline frontier.

This prevents the runtime from starting fresh work for an older input after newer relationship history already exists.

Once a `CompanionOutput` has been adopted, recovery follows the adoption/presentation boundary rather than regenerating merely because later operational state changed.

## Crash-injection boundaries

The acceptance suite injects complete runtime loss after each durable boundary:

```text
INPUT_ADMITTED
INVESTIGATION_STARTED
OBSERVATION_STARTED
WORLD_CAPTURED
WORLD_RESULT_ADMITTED
CONTEXT_PROJECTION_BUILT
MODEL_INVOCATION_STARTED
GENERATED_OUTPUT_COMMITTED
OUTPUT_TARGET_RESOLVED
COMPANION_OUTPUT_ADOPTED
PRESENTED
```

For every boundary, a fresh runtime opens the same durable database and resumes with no in-memory state from the previous runtime.

The final assertions require:

```text
one logical Investigation
one accepted WorldSourceCapture
one admitted WorldResult
one reusable ContextProjection
one GeneratedOutput
one OutputTarget
one CompanionOutput
one presented Timeline event
```

The two deliberate retry boundaries differ:

```text
crash after Observation STARTED
→ old Observation remains STARTED
→ retry creates a second Observation
→ only the second Observation owns the successful capture

crash after ModelInvocation IN_PROGRESS
→ old invocation reconciles to UNKNOWN
→ retry creates a second ModelInvocation
→ only the second invocation owns GeneratedOutput
```

## Provenance after recovery

The final presented response still has the same evidence and cognition lineage:

```text
remembered segment
→ PersonClaim
→ EvidenceItem
→ counterpart InteractionEvent

checked-world segment
→ WorldResult
→ EvidenceItem
→ WorldSourceCapture
→ Observation
→ Investigation

presented response
→ CompanionOutput
→ GeneratedOutput
→ ModelInvocation
→ ContextProjection
```

Process death changes none of those ownership relationships.

## Scope

This coordinator is intentionally F4-specific.

It does not introduce:

```text
effectful Actions
DelegatedTask execution
proactive contact
background scheduling
multi-channel fallback
rich embodiment
```

It also does not create a general workflow engine.

The checkpoint proves only that the existing foundation can be composed into one restart-safe reactive path without transcript reconstruction or duplicate semantic effects.

## Next boundary

The next implementation increment should reduce the remaining F4 fixture assumptions while preserving the same runtime contract:

```text
controlled source-specific world extraction
real configured model-provider contract verification
runtime configuration boundary
operator-visible recovery diagnostics
```

Broader delegated work or proactive execution should remain outside the implementation until the reactive foundation is stable under real configured providers.
