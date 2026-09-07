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
    │       → optional bounded prior-Timeline context
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

For `CONVERSATIONAL_RESPONSE`, the runtime invokes `FoundationConversationalResponseCoordinator`. A self-contained form builds a ContextProjection over pinned Self/Relationship/current-input state. A bounded contextual `that`/`it` form may additionally select exactly the immediately preceding completed presented exchange through the semantic projection service. Neither form projects personal/world propositions, starts an Investigation, or admits memory.

For `WORLD_QUESTION`, the runtime delegates to the checked `FoundationResponseCoordinator`, which performs fresh acquisition and evidence-backed world-result admission before cognition.

Unsupported input fails closed before provider work.

```text
interaction classification ≠ model authority
memory admission ≠ response obligation
conversation ≠ fresh-world investigation
prior Timeline context ≠ admitted memory
reference resolution ≠ model-selected history
unsupported input ≠ inferred route
```

See [F4 Interaction Purpose Gate](F4_INTERACTION_PURPOSE_GATE.md), [F4 Conversational Response Path](F4_CONVERSATIONAL_RESPONSE.md), and [F4 Prior-Timeline Context Selection](F4_PRIOR_TIMELINE_CONTEXT.md).

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

## Conversational prior-Timeline rendering

For the narrow contextual grammar, the semantic service may persist exact projection membership:

```text
prior COUNTERPART_INPUT
prior COMPANION_PRESENTED_OUTPUT replying to it
current contextual COUNTERPART_INPUT
```

Only the two prior events are rendered into the optional provider field:

```text
prior_timeline_context {
    selection_policy: IMMEDIATE_PREVIOUS_PRESENTED_EXCHANGE
    events: [...]
}
```

The current input remains the normal `current_input` field. Personal and world context arrays remain empty.

```text
prior_timeline_context ≠ MemoryClaim
prior_timeline_context ≠ WorldResult
prior presented Companion output ≠ factual source authority
```

The rendering contract is versioned. New model invocations use the current renderer identity; already-durable ModelInvocations retain the renderer version that actually produced their request.

## Model response contracts

The JSON model adapter derives its bounded response contract from the Alsoul-owned provider context shape rather than asking the model to choose the semantic path.

For a checked projection containing exactly one eligible personal item and one current checked world item, the required sequence remains:

```text
REMEMBERED_COUNTERPART_STATEMENT
CURRENT_CHECKED_WORLD
COMPANION_INTERPRETATION
```

For both self-contained and bounded contextual conversational projections:

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

A contextual projection may contain `prior_timeline_context`; that does not transform the expression into an evidence-backed proposition.

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

This prevents a lower-level caller from bypassing the high-level purpose boundary and forcing a social or contextual utterance through fresh-world work.

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

Conversational recovery begins at the input/projection boundary because no world work exists. For a contextual interaction, a committed ContextProjection already contains the exact prior-event selection. Recovery reuses that selection rather than searching Timeline history again. A committed GeneratedOutput is recovered rather than regenerated, and adopted output is re-presented idempotently when needed.

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

Diagnostics intentionally exclude user message text, selected prior Timeline content, captured source content, generated response text, credentials, and authorization headers. They remain derived and non-authoritative.

## Failure semantics

A checked cross-origin source response may preserve a successful Observation/Capture/EvidenceItem while rejecting WorldResult derivation. This is intentional: acquisition truth does not imply proposition admissibility.

An invalid model contract response remains a rejected provider attempt. It does not become CompanionOutput or shared-history presentation.

A conversational GeneratedOutput that violates the source-free expression contract can remain durable provider-return history while adoption fails; it does not become CompanionOutput.

A bounded contextual form with no eligible immediately preceding exchange fails before provider execution. The current input remains canonical Timeline history; Alsoul does not guess a referent or inject a fallback transcript window.

An unsupported high-level interaction may already exist in canonical counterpart history, but the purpose gate stops before provider execution.

## Configuration persistence rule

This checkpoint does not add a canonical runtime-configuration table.

Provider routes are deployment/runtime configuration rather than Person or Relationship state. If later product semantics require user-governed provider or source selection, that should be modeled explicitly rather than silently promoting deployment configuration into companion identity.

## Acceptance coverage

The executable suite verifies configured HTTPS world/model/presentation routes; source-origin-pinned checked interpretation; transport credential separation; the synthetic checked model probe; memory-only interaction without provider work; route fencing; bounded conversational classification and execution without Investigation/WorldResult; the source-free conversational model contract; rejection of conversational source attribution; exact immediate-prior Timeline selection for the contextual grammar; fail-closed behavior when prior context is unavailable or crosses a conversation boundary; recovery of committed contextual generation without history reselection or regeneration; checked-response rejection of conversational input; local surface conversational replay across complete recomposition; and the existing evidence-backed checked-response path.

The configured runtime remains the bounded F4 slice. It does not introduce general conversational routing, arbitrary coreference resolution, generic transcript windows, semantic Timeline search, cross-thread contextual resolution, external Actions, durable delegated work, triggers, schedules, proactive contact, multi-channel fallback, or rich embodiment.
