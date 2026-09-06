# F4 Configured Reactive Runtime

## Purpose

This checkpoint closes the gap between deterministic acceptance fixtures and a configured reactive runtime without widening semantic authority.

The F4 chain remains:

```text
Counterpart input
→ Investigation
→ Observation
→ WorldSourceCapture
→ EvidenceItem
→ bounded source interpretation
→ WorldResult admission
→ ContextProjection
→ ModelInvocation
→ GeneratedOutput
→ CompanionOutput
→ presented Timeline event
```

The new runtime boundary adds configuration, source-specific interpretation, provider contract probing, and operator diagnostics around the existing semantic services. None of those concerns become CompanionPerson identity, memory, world truth, or shared-history authority.

## Configuration boundary

`FoundationRuntimeConfig` contains only non-secret route configuration:

```text
WorldRuntimeConfig
    HTTPS locator
    timeout

ModelRuntimeConfig
    HTTPS endpoint
    provider binding reference
    model reference
    timeout
```

`RuntimeSecrets` is separate transport-only state. Model authorization material is supplied when adapters are constructed and is never written into ContextProjection, ModelInvocation identity fields, GeneratedOutput, diagnostics, or public configuration snapshots.

```text
configuration ≠ credential
credential ≠ identity
credential ≠ authority
```

The configured runtime requires HTTPS for both world acquisition and model generation. Embedded URL credentials and fragments are rejected.

## Source-specific interpretation

Raw provider return bytes do not become a WorldResult.

The runtime first persists the acquisition as normal:

```text
Observation
→ WorldSourceCapture
→ EvidenceItem
```

It then loads the exact persisted capture into a bounded `WorldResultExtractor`.

For the current F4 slice, `F4JsonMemoryRequirementExtractor` accepts one JSON semantic contract:

```text
minimum_memory_gb: positive integer
```

A configured production runtime also pins the expected HTTPS source origin. A capture from another origin is retained as historical acquisition evidence but is rejected for WorldResult derivation under that configured source contract.

```text
capture persisted
≠ source contract satisfied

source contract satisfied
≠ WorldResult admitted
```

The extractor only returns an `ExtractedWorldResult` proposal. `FoundationServices.admit_world_result` remains the authoritative admission boundary and independently validates evidence lineage and semantic support.

## ConfiguredFoundationRuntime

`ConfiguredFoundationRuntime` composes:

```text
FoundationServices
FoundationResponseCoordinator
HttpWorldAdapter
F4JsonMemoryRequirementExtractor
JsonModelProviderAdapter
FoundationRuntimeDiagnostics
```

The caller supplies only durable response identity and presentation-route references:

```text
relationship_id
current_input_event_id
surface_binding_id
channel_binding_id
```

Provider route configuration is constructed outside canonical companion state.

The runtime still resumes from the furthest trustworthy durable stage. Reconfiguration or process replacement therefore does not recreate history or convert provider state into companion state.

## Model-provider contract probe

The configured runtime exposes an operator-only model contract probe.

The probe sends synthetic F4 context and verifies that the configured endpoint returns the required semantic sequence:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

It also verifies that remembered and checked segments preserve the synthetic claim/result references and that the interpretation segment does not claim an external source.

The probe is deliberately outside CompanionPerson cognition:

```text
operational contract probe
≠ ContextProjection-backed cognition
≠ ModelInvocation
≠ GeneratedOutput
≠ Timeline event
```

No user message, memory, world result, or relationship state is used by the probe, and the probe writes no canonical cognition rows.

## Operator diagnostics

`FoundationRuntimeDiagnostics` derives a content-free view of one response from canonical rows.

It can expose:

```text
recovery stage
next safe operation
Investigation identity
Observation identities + statuses
WorldResult identities
ModelInvocation identities + outcomes
provider/model references
projection/generated/adopted/presented identities
reuse/recovery blockers
```

It intentionally excludes:

```text
user message text
captured source content
generated response text
credentials
provider authorization headers
```

Diagnostics remain derived and non-authoritative.

Example next-operation values include:

```text
START_INVESTIGATION
START_WORLD_ACQUISITION
RECONCILE_WORLD_ACQUISITION
INTERPRET_WORLD_CAPTURE
BUILD_CONTEXT_PROJECTION
START_MODEL_INVOCATION
RECONCILE_MODEL_ATTEMPT
ADOPT_GENERATED_OUTPUT
PRESENT_ADOPTED_OUTPUT
NONE
```

These values describe what the operator/runtime may safely attempt next. They do not create new lifecycle authority.

## Failure semantics

A cross-origin source response can produce:

```text
Observation SUCCEEDED
WorldSourceCapture persisted
EvidenceItem persisted
WORLD_EXTRACTION_REJECTED
no WorldResult
```

This is intentional. Alsoul can truthfully retain what it acquired without claiming that the source was admissible under the configured world contract.

Likewise, an invalid model contract response remains a rejected provider attempt. It does not become CompanionOutput or shared-history presentation.

## Configuration persistence rule

This checkpoint does not add a canonical runtime-configuration table.

Provider routes are deployment/runtime configuration rather than Person or Relationship state. If later product semantics require user-governed provider or source selection, that should be modeled explicitly rather than silently promoting deployment configuration into companion identity.

## Acceptance coverage

The executable suite now verifies:

- configured HTTPS world and model routes;
- strict same-origin world interpretation;
- capture retention without WorldResult admission when source policy rejects the capture;
- transport credential separation from public configuration and canonical provider identity fields;
- a configured model contract probe using synthetic context only;
- no ModelInvocation or GeneratedOutput created by the operator probe;
- operator diagnostics before and after a complete reactive response;
- the configured network-adapter path through memory, fresh world evidence, model generation, adoption, and presentation.

The configured path is still the F4 reactive slice. It does not introduce external Actions, durable delegated work, triggers, schedules, proactive contact, multi-channel fallback, or rich embodiment.
