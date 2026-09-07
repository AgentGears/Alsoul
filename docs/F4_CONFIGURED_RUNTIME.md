# F4 Configured Runtime

## Purpose

This checkpoint closes the gap between deterministic acceptance fixtures and a configured F4 runtime without widening semantic authority.

The runtime exposes two execution levels:

```text
ConfiguredFoundationRuntime.interact
    ↓
bounded interaction-purpose gate
    ├── MEMORY_STATEMENT
    │       → evidence-grounded memory admission
    │       → stop
    │
    ├── CONVERSATIONAL_RESPONSE
    │       → source-free ContextProjection
    │       → model generation
    │       → conversational adoption
    │       → first-party presentation
    │
    └── WORLD_QUESTION
            → checked fresh-world response path

ConfiguredFoundationRuntime.respond
    ↓
already-selected WORLD_QUESTION response/recovery path only
```

The configured runtime adds bounded interaction routing, configuration, provider interpretation, provider contract enforcement, and diagnostics around Alsoul-owned semantic services. None of those concerns become CompanionPerson identity, memory, world truth, or shared-history authority.

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

It uses `F4InteractionPurposeGate` to derive one implemented bounded purpose:

```text
MEMORY_STATEMENT
CONVERSATIONAL_RESPONSE
WORLD_QUESTION
```

The gate validates that the current input belongs to the supplied relationship, surface binding, and channel binding before semantic continuation.

For `MEMORY_STATEMENT`, the runtime invokes `F4CounterpartMemoryAdmission` and returns the memory outcome without fresh-world or cognition work.

For `CONVERSATIONAL_RESPONSE`, the runtime invokes `FoundationConversationalResponseCoordinator`. That path builds a minimal ContextProjection with no projected personal or world propositions, performs one model invocation under the source-free `COMPANION_EXPRESSION` contract, adopts the candidate through a typed conversational output boundary, and uses the normal first-party presentation gate. It creates no Investigation or WorldResult.

For `WORLD_QUESTION`, the runtime delegates to the checked `FoundationResponseCoordinator`, which performs fresh acquisition and evidence-backed world-result admission before cognition.

Unsupported input fails closed before provider work.

```text
interaction classification ≠ model authority
memory admission ≠ response obligation
conversation ≠ fresh-world investigation
unsupported input ≠ inferred route
```

See [F4 Interaction Purpose Gate](F4_INTERACTION_PURPOSE_GATE.md) and [F4 Conversational Response Path](F4_CONVERSATIONAL_RESPONSE.md).

## Checked source-specific interpretation

Raw provider return bytes do not become a WorldResult.

The checked `WORLD_QUESTION` path first persists actual acquisition:

```text
Observation
→ WorldSourceCapture
→ EvidenceItem
```

It then loads the exact persisted capture into a bounded `WorldResultExtractor`.

For the current F4 checked slice, `F4JsonMemoryRequirementExtractor` accepts one JSON semantic contract:

```text
minimum_memory_gb: positive integer
```

A configured runtime pins the expected HTTPS source origin. A capture from another origin is retained as historical acquisition evidence but rejected for WorldResult derivation under that configured source contract.

```text
capture persisted
≠ source contract satisfied

source contract satisfied
≠ WorldResult admitted
```

The extractor only returns an `ExtractedWorldResult` proposal. `FoundationServices.admit_world_result` remains the authoritative admission boundary and independently validates evidence lineage and semantic support.

The conversational path does not invoke this acquisition/interpretation chain.

## Model response contracts

The JSON model adapter derives its bounded response contract from the Alsoul-owned provider context shape rather than asking the model to choose the semantic path.

For a checked projection containing exactly one eligible personal item and one current checked world item, the required sequence remains:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

For the current conversational projection:

```text
personal_context = []
world_context = []
```

and the required sequence is exactly:

```text
COMPANION_EXPRESSION
```

with:

```text
source_ref = null
```

Other provider-context shapes are outside the current F4 model wire contract and fail closed.

```text
provider contract selection ≠ model routing authority
source-free expression ≠ evidence-backed proposition
```

## ConfiguredFoundationRuntime composition

`ConfiguredFoundationRuntime` composes:

```text
FoundationServices
F4InteractionPurposeGate
F4CounterpartMemoryAdmission
FoundationConversationalResponseCoordinator
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

## Lower-level checked response fence

`ConfiguredFoundationRuntime.respond` remains available for explicit checked-response recovery/control. It is not a general response primitive.

Before invoking the checked coordinator it re-runs the deterministic purpose gate against the canonical input and exact route. Only `WORLD_QUESTION` may continue.

```text
CONVERSATIONAL_RESPONSE → respond
    = RESPONSE_PATH_PURPOSE_MISMATCH
    = no world provider work
    = no model provider work
```

This prevents a lower-level caller from bypassing the high-level purpose boundary and forcing a social utterance through fresh-world work.

## Recovery

Both response-producing paths reuse the canonical response recovery graph:

```text
INPUT_ADMITTED
PROJECTION_READY
MODEL_ATTEMPT_UNRESOLVED
GENERATED
ADOPTED
PRESENTED
```

Checked response recovery may additionally recover Investigation, capture, and WorldResult stages before projection.

Conversational recovery begins at the input/projection boundary because no world work exists. A committed conversational GeneratedOutput is recovered rather than regenerated, and adopted output is re-presented idempotently when needed.

Reconfiguration or process replacement therefore does not recreate history or convert provider state into companion state.

## Model-provider contract probe

The configured runtime exposes an operator-only model contract probe for the checked-response wire shape.

The probe sends synthetic F4 context and verifies:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

It also verifies the synthetic claim/result references and source-free interpretation segment.

The probe is outside CompanionPerson cognition:

```text
operational contract probe
≠ ContextProjection-backed cognition
≠ ModelInvocation
≠ GeneratedOutput
≠ Timeline event
```

No user message, memory, world result, or relationship state is used by the probe, and it writes no canonical cognition rows.

## Operator diagnostics

`FoundationRuntimeDiagnostics` derives a content-free response view from canonical rows. Its detailed world-stage `next_action` values are designed for the checked response path; response-level recovery stages remain valid for conversational output as well.

Diagnostics intentionally exclude user message text, captured source content, generated response text, credentials, and authorization headers. They remain derived and non-authoritative.

## Failure semantics

A checked cross-origin source response may preserve a successful Observation/Capture/EvidenceItem while rejecting WorldResult derivation. This is intentional: acquisition truth does not imply proposition admissibility.

An invalid model contract response remains a rejected provider attempt. It does not become CompanionOutput or shared-history presentation.

A conversational GeneratedOutput that violates the source-free expression contract can remain durable provider-return history while adoption fails; it does not become CompanionOutput.

An unsupported high-level interaction may already exist in canonical counterpart history, but the purpose gate stops before provider execution.

## Configuration persistence rule

This checkpoint does not add a canonical runtime-configuration table.

Provider routes are deployment/runtime configuration rather than Person or Relationship state. If later product semantics require user-governed provider or source selection, that should be modeled explicitly rather than silently promoting deployment configuration into companion identity.

## Acceptance coverage

The executable suite verifies configured HTTPS world/model/presentation routes; source-origin-pinned checked interpretation; transport credential separation; the synthetic checked model probe; memory-only interaction without provider work; route fencing; bounded conversational classification and execution without Investigation/WorldResult; the source-free conversational model contract; rejection of conversational source attribution; recovery of committed conversational generation without regeneration; checked-response rejection of conversational input; local surface conversational replay across complete recomposition; and the existing evidence-backed checked-response path.

The configured runtime remains the bounded F4 slice. It does not introduce general conversational routing, deictic prior-history resolution, external Actions, durable delegated work, triggers, schedules, proactive contact, multi-channel fallback, or rich embodiment.