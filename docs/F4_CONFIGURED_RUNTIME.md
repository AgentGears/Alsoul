# F4 Configured Runtime

## Purpose

This checkpoint closes the gap between deterministic acceptance fixtures and a configured F4 runtime without widening semantic authority.

The runtime now exposes two distinct execution levels:

```text
ConfiguredFoundationRuntime.interact
    ↓
bounded interaction-purpose gate
    ├── MEMORY_STATEMENT → evidence-grounded memory admission → stop
    └── WORLD_QUESTION   → configured reactive response path

ConfiguredFoundationRuntime.respond
    ↓
already-selected WORLD_QUESTION response/recovery path
```

The checked-response chain remains:

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

The configured runtime adds interaction routing, configuration, source-specific interpretation, provider contract probing, and operator diagnostics around the existing semantic services. None of those concerns become CompanionPerson identity, memory, world truth, or shared-history authority.

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

PresentationRuntimeConfig
    HTTPS endpoint
    timeout
```

`RuntimeSecrets` is separate transport-only state. Model authorization material is supplied when adapters are constructed and is never written into ContextProjection, ModelInvocation identity fields, GeneratedOutput, diagnostics, or public configuration snapshots.

```text
configuration ≠ credential
credential ≠ identity
credential ≠ authority
```

The configured runtime requires HTTPS for world acquisition, model generation, and configured presentation. Embedded URL credentials and fragments are rejected.

## Interaction-purpose boundary

`ConfiguredFoundationRuntime.interact` is the high-level F4 interaction entry point after trusted ingress has already committed a canonical `COUNTERPART_INPUT`.

It uses `F4InteractionPurposeGate` to derive one of the only two purposes implemented by F4:

```text
MEMORY_STATEMENT
WORLD_QUESTION
```

The gate validates that the current input belongs to the supplied relationship, surface binding, and channel binding before the runtime continues. This prevents a high-level caller from pairing one canonical event with another route.

For `MEMORY_STATEMENT`, the runtime invokes `F4CounterpartMemoryAdmission` and returns the memory outcome without creating fresh-world or cognition state.

For `WORLD_QUESTION`, the runtime delegates to `respond` and the existing recovery-safe response coordinator.

Unsupported input fails closed before provider work.

```text
interaction classification ≠ model authority
memory admission ≠ response obligation
unsupported input ≠ inferred route
```

See [F4 Interaction Purpose Gate](F4_INTERACTION_PURPOSE_GATE.md) for the bounded routing contract.

## Source-specific interpretation

Raw provider return bytes do not become a WorldResult.

The checked-response path first persists the acquisition as normal:

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

A configured runtime also pins the expected HTTPS source origin. A capture from another origin is retained as historical acquisition evidence but is rejected for WorldResult derivation under that configured source contract.

```text
capture persisted
≠ source contract satisfied

source contract satisfied
≠ WorldResult admitted
```

The extractor only returns an `ExtractedWorldResult` proposal. `FoundationServices.admit_world_result` remains the authoritative admission boundary and independently validates evidence lineage and semantic support.

## ConfiguredFoundationRuntime composition

`ConfiguredFoundationRuntime` composes:

```text
FoundationServices
F4InteractionPurposeGate
F4CounterpartMemoryAdmission
FoundationResponseCoordinator
HttpWorldAdapter
F4JsonMemoryRequirementExtractor
JsonModelProviderAdapter
JsonFirstPartyPresentationAdapter
FoundationRuntimeDiagnostics
```

The high-level caller supplies durable interaction identity and route references:

```text
relationship_id
current_input_event_id
surface_binding_id
channel_binding_id
```

Provider route configuration is constructed outside canonical companion state.

For an interaction already known to be on the checked-response path, lower-level `respond` keeps the existing recovery contract. It resumes from the furthest trustworthy durable stage. Reconfiguration or process replacement therefore does not recreate history or convert provider state into companion state.

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

`FoundationRuntimeDiagnostics` derives a content-free view of one checked response from canonical rows.

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

These values describe what the operator/runtime may safely attempt next on the checked-response path. They do not create new lifecycle authority.

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

An unsupported high-level interaction is different: trusted ingress may already have preserved the canonical counterpart input, but the purpose gate stops before Investigation or provider execution.

## Configuration persistence rule

This checkpoint does not add a canonical runtime-configuration table.

Provider routes are deployment/runtime configuration rather than Person or Relationship state. If later product semantics require user-governed provider or source selection, that should be modeled explicitly rather than silently promoting deployment configuration into companion identity.

## Acceptance coverage

The executable suite verifies:

- configured HTTPS world, model, and presentation routes;
- strict same-origin world interpretation;
- capture retention without WorldResult admission when source policy rejects the capture;
- transport credential separation from public configuration and canonical provider identity fields;
- a configured model contract probe using synthetic context only;
- no ModelInvocation or GeneratedOutput created by the operator probe;
- operator diagnostics before and after a complete checked response;
- a memory-only high-level interaction that creates admitted memory but no Investigation, ModelInvocation, CompanionOutput, or presented Timeline output;
- exact memory-only replay without duplicate memory or provider work;
- high-level route fencing to the canonical relationship/surface/channel event;
- unsupported high-level interaction failing before provider work; and
- the configured checked path through memory retrieval, fresh world evidence, model generation, adoption, and presentation.

The configured path is still the bounded F4 slice. It does not introduce general conversational routing, external Actions, durable delegated work, triggers, schedules, proactive contact, multi-channel fallback, or rich embodiment.
