# F4 Controlled Provider Integration

## Purpose

This checkpoint connects the executable F4 foundation to replaceable network providers without transferring Alsoul-owned authority to those providers.

The semantic chains remain unchanged:

```text
Investigation
→ Observation
→ WorldSourceCapture
→ EvidenceItem
→ WorldResult
```

and:

```text
ContextProjection
→ ModelInvocation
→ GeneratedOutput
→ CompanionOutput
→ presented Timeline event
```

A network response can advance one of those chains only through the existing semantic application-service boundary.

## World acquisition runner

`WorldAcquisitionRunner` owns one concrete read-only acquisition attempt under an already-created `Investigation`.

Its order is:

```text
persist Observation(STARTED)
→ call WorldAcquisitionAdapter
→ persist exact source capture
→ create EvidenceItem
→ mark Observation(SUCCEEDED)
```

If the adapter fails before an acceptable capture is returned:

```text
Observation(STARTED)
→ Observation(FAILED)
```

No `WorldResult` is created by the runner.

This preserves:

```text
transport success ≠ world truth
captured source ≠ admitted result
```

A later `AdmitWorldResult` operation must still validate the evidence lineage and result semantics.

## Model generation runner

`ModelGenerationRunner` binds one provider attempt to one immutable `ContextProjection`.

Its order is:

```text
render pinned ContextProjection
→ persist ModelInvocation(IN_PROGRESS)
→ dispatch to ModelProviderAdapter
→ persist GeneratedOutput
→ mark ModelInvocation(SUCCEEDED)
```

Provider identity is taken from the configured adapter and recorded on the invocation. It does not become `CompanionPerson` identity.

A successful generation still stops at:

```text
GeneratedOutput
```

Adoption and presentation remain explicit later boundaries.

## Failure semantics

The adapter layer distinguishes a definite unusable provider result from an uncertain transport outcome.

```text
AdapterRejected
→ ModelInvocation(FAILED)

AdapterOutcomeUnknown
→ ModelInvocation(UNKNOWN)
```

An unexpected exception after model dispatch begins is conservatively treated as unknown.

This preserves:

```text
definite failure ≠ unknown outcome
model retry ≠ mutation of prior ModelInvocation
```

A retry therefore creates a new `ModelInvocation` while retaining the old attempt.

## HTTPS model endpoint

`JsonModelProviderAdapter` is a production-capable transport for an explicitly configured HTTPS endpoint that implements Alsoul's F4 response wire contract.

The adapter sends:

```text
model_ref
provider_context
response contract metadata
```

and expects a structured `FoundationResponseDraft`.

The provider-facing credential is transport configuration only. It is placed in the request authorization header and is not inserted into:

```text
ContextProjection
provider context
semantic response payload
ModelInvocation provider identity
```

The configured endpoint must use HTTPS. Invalid response shape, non-success HTTP responses, or invalid semantic segment kinds are rejected before they can be treated as a usable generation result.

The host still validates provenance-bearing response semantics again at `CompanionOutput` adoption.

## Provider-independent identity

The adapter contract exposes stable provider-side references:

```text
provider_binding_ref
model_ref
```

These are execution provenance only.

They do not define:

```text
CompanionPerson
SelfModel
RelationshipState
MemoryClaim
WorldResult
```

Changing provider or model creates different invocation provenance while the Person and relationship remain the same.

## Acceptance coverage

The executable suite now verifies that:

```text
Observation exists before network acquisition begins
failed acquisition creates no WorldSourceCapture
successful acquisition does not automatically create WorldResult
ModelInvocation exists before model dispatch begins
provider/model refs come from configured adapter identity
generation produces no automatic CompanionOutput or Timeline presentation
uncertain model transport becomes UNKNOWN
definite provider rejection becomes FAILED
transport credentials are absent from semantic request body
HTTPS model endpoint is required
invalid structured provider output is rejected
```

## Scope

This checkpoint does not add provider credentials to canonical F4 persistence and does not implement the broader authority plane.

It also does not add:

```text
Permission / Approval / Action / Effect
DelegatedTask / WorkRun
proactive contact
multi-channel external delivery
rich streaming modality
```

Those remain outside the walking skeleton.

## Next boundary

The next safe increment is provider recovery hardening:

```text
orphaned IN_PROGRESS invocation reconciliation
new-invocation retry after FAILED / UNKNOWN
projection reuse eligibility before retry
acquisition retry as a new Observation
provider replacement acceptance through the runner path
```

The governing rule remains:

> Provider execution may supply candidate material, but only Alsoul-owned durable semantic transitions can turn that material into evidence, results, adopted expression, or shared history.
