# F4 Provider Recovery Hardening

## Purpose

This checkpoint hardens the controlled F4 provider path across process loss, retry, provider replacement, and stale-context recovery without widening semantic authority.

The governing distinctions remain:

```text
ModelInvocation ≠ GeneratedOutput ≠ CompanionOutput ≠ presentation
FAILED ≠ UNKNOWN
provider retry ≠ mutation of the prior attempt
ContextProjection persistence ≠ ContextProjection reuse eligibility
Observation retry ≠ reuse of the prior Observation
provider/model identity ≠ CompanionPerson
```

## Model attempt recovery

A `ModelInvocation(IN_PROGRESS)` is a durable record that one provider attempt began. After complete runtime loss, its final provider outcome cannot be inferred from the absence of a `GeneratedOutput`.

Recovery therefore derives:

```text
eligible ContextProjection
+ IN_PROGRESS ModelInvocation
+ no recoverable GeneratedOutput
→ MODEL_ATTEMPT_UNRESOLVED
```

No retry is dispatched from that state.

A known process-loss boundary may explicitly reconcile the orphaned attempt:

```text
MODEL_ATTEMPT_UNRESOLVED
→ classify prior ModelInvocation as UNKNOWN
→ PROJECTION_READY
```

`UNKNOWN` means the original attempt's final provider outcome was not recovered. It does not mean the provider definitely failed.

The reconciliation boundary does not invoke a provider. A later retry is a separate operation.

## Retry identity

Every retry creates a new `ModelInvocation`.

```text
MI1 FAILED or UNKNOWN
→ retry decision
→ MI2 IN_PROGRESS
```

The prior attempt remains immutable history except for its permitted terminal outcome transition.

A new attempt is blocked while another attempt for the same projection remains `IN_PROGRESS`.

A new attempt is also blocked after a successful `GeneratedOutput` already exists. Recovery must continue from the durable generated candidate rather than generate another candidate for the same semantic response context.

This preserves:

```text
retry after FAILED/UNKNOWN = new ModelInvocation
orphaned IN_PROGRESS ≠ permission to retry
GeneratedOutput exists = recover, do not regenerate
```

## ContextProjection reuse eligibility

An immutable `ContextProjection` may be durable but no longer eligible for another provider invocation.

For the F4 reactive path, reuse requires all of the following to remain true:

```text
purpose = RESPOND_TO_INTERACTION
current input still exists in the same relationship
current input is projected
current input is the pinned Timeline frontier
pinned Self revision is still current
pinned Relationship revision is still current
relationship Timeline frontier has not advanced
```

The current-input frontier rule prevents a projection built for an older input from becoming executable merely because it was built after newer relationship history already existed.

If any of those fences changed, the projection remains historical state but is not reused.

Recovery then falls back to the earlier semantic stage:

```text
stale ContextProjection
→ INPUT_ADMITTED
→ rebuild ContextProjection from current canonical state
```

The current implementation reports a typed reuse blocker such as:

```text
SELF_REVISION_CHANGED
RELATIONSHIP_REVISION_CHANGED
TIMELINE_ADVANCED
CURRENT_INPUT_NOT_AT_FRONTIER
CURRENT_INPUT_INVALID
```

Provider execution is fenced at the application-service boundary as well as in recovery assessment, so a caller cannot bypass stale-projection detection by invoking the runner directly.

## Provider replacement

Provider identity belongs to execution provenance, not companion identity.

A retry may therefore use another configured provider/model pair while preserving the same:

```text
CompanionPerson
CounterpartPerson
RelationshipState
ContextProjection
```

when that projection remains reusable.

The resulting retry chain is:

```text
ContextProjection CP1
→ ModelInvocation MI1 / provider route A / FAILED or UNKNOWN
→ ModelInvocation MI2 / provider route B / SUCCEEDED
→ GeneratedOutput G1
```

Provider replacement does not create a new person or relationship.

## Acquisition retry

World acquisition follows the same attempt-identity principle at the Observation boundary.

An orphaned `Observation(STARTED)` after process loss is not treated as successful evidence and is not reused for a new acquisition.

Retry creates a distinct Observation:

```text
Observation O1 / STARTED / no recoverable capture
→ process loss
→ retry
→ Observation O2 / STARTED
→ WorldSourceCapture S2
→ EvidenceItem E2
→ O2 SUCCEEDED
```

O1 remains historical attempt state. The successful capture belongs only to O2.

This preserves:

```text
retry ≠ overwrite prior Observation
orphaned STARTED ≠ acquired world evidence
new capture ≠ retroactive success of old Observation
```

## Recovery stages

The F4 response recovery path now derives:

```text
INPUT_ADMITTED
PROJECTION_READY
MODEL_ATTEMPT_UNRESOLVED
GENERATED
ADOPTED
PRESENTED
```

`MODEL_ATTEMPT_UNRESOLVED` is intentionally between projection readiness and generated output. It prevents a process restart from turning uncertainty into an implicit duplicate dispatch.

## Acceptance coverage

The executable suite verifies that:

```text
orphaned IN_PROGRESS model attempt is detected after process loss
blind retry is blocked while that attempt is unresolved
explicit process-loss reconciliation changes it to UNKNOWN
retry then creates a different ModelInvocation
FAILED and UNKNOWN attempts may retry through a replacement provider
provider/model replacement does not change Person or Relationship identity
Timeline advancement makes an old ContextProjection non-reusable
non-frontier reactive input cannot start provider execution
stale ContextProjection cannot be invoked directly through the runner
existing GeneratedOutput is recovered rather than regenerated
acquisition retry after an orphaned STARTED attempt creates a new Observation
successful retry capture belongs only to the new Observation
```

## Scope

This checkpoint still does not introduce effectful external Actions, delegated background work, proactive contact, multi-channel external delivery, or rich modality.

It also does not claim that every provider-side economic or operational consequence of an unknown model request can be reversed. The F4 guarantee is narrower: provider uncertainty cannot silently become Alsoul semantic truth, duplicate adopted output, or duplicate presentation.

## Next boundary

The next implementation increment should connect these recovery rules to a small end-to-end runtime coordinator that can resume the walking skeleton from the furthest durable stage:

```text
input
→ investigation/acquisition
→ projection
→ provider generation
→ adoption
→ presentation
```

with process-death injection at each durable boundary and no transcript-based reconstruction.
