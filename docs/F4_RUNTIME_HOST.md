# F4 Runtime Host

**Status:** Implemented foundation checkpoint

The configured F4 slice has a narrow process-facing host. The host turns persistence, recovery, trusted first-party ingress, bounded interaction-purpose routing, provider execution, and presentation acceptance into an executable process without creating a second source of semantic authority.

## Boundary

```text
process configuration
    +
ephemeral transport secret
    +
pre-existing compatible F4 database
        ↓
alsoul-host
        ├── readiness / diagnostics
        ├── trusted first-party ingress
        ├── bounded high-level interaction
        │       ├── MEMORY_STATEMENT → memory admission → stop
        │       └── WORLD_QUESTION   → checked response path
        └── lower-level checked-response recovery
```

The host is deliberately not a bootstrapper, schema creator, public network authentication service, task scheduler, or authority service.

Permanent distinctions:

```text
runtime configuration ≠ canonical companion state
runtime configuration ≠ credential
credential ≠ identity
host readiness ≠ provider readiness
operator diagnostic ≠ canonical runtime state
trusted transport assertion ≠ model inference
interaction classification ≠ model authority
memory admission ≠ response obligation
CompanionOutput ≠ presentation attempt ≠ sink acceptance ≠ Timeline presentation
presented ≠ read/heard/understood
bootstrap administration ≠ ordinary runtime
```

## Host configuration

The host reads one strict JSON document. Unknown fields fail closed. Relative filesystem paths are resolved relative to the configuration file.

Configuration version 2 requires the existing database plus explicit world, model, and first-party presentation routes. HTTPS trust is process infrastructure rather than evidence, identity, permission, or canonical companion state.

The model authorization token remains absent from the configuration file and, if needed, is supplied only through:

```text
ALSOUL_MODEL_AUTHORIZATION_TOKEN
```

The host does not persist or emit it.

## Readiness

`ready` performs local startup checks only:

```text
configuration parses
↓
database file already exists
↓
database readable
↓
required F4 tables/columns exist
↓
foreign-key enforcement active
↓
READY
```

It performs no world, model, or presentation I/O. A structurally compatible but identity-empty store may pass structural readiness, while trusted ingress still fails closed until the required identity/presence bindings exist.

## Commands

### Readiness

```text
alsoul-host --config ./host.json ready
```

### Trusted first-party input admission

```text
cat envelope.json | alsoul-host --config ./host.json ingest
```

`ingest` resolves pre-existing identity, relationship, surface, and channel bindings and commits exactly one canonical `COUNTERPART_INPUT`. The model never participates in identity resolution.

### High-level one-shot interaction

```text
cat envelope.json | alsoul-host --config ./host.json interact
```

`interact` now means:

```text
trusted transport assertion
↓
COUNTERPART_INPUT committed
↓
ConfiguredFoundationRuntime.interact
↓
F4InteractionPurposeGate
├── MEMORY_STATEMENT
│   ↓
│   F4CounterpartMemoryAdmission
│   ↓
│   durable Evidence + Claim state
│   ↓
│   return successful memory outcome
│   no provider work
│
└── WORLD_QUESTION
    ↓
    existing recovery-safe checked response
```

The purpose gate derives classification from the immutable canonical event and fences the event to the exact admitted relationship, surface binding, and channel binding. Route mismatch fails before memory admission or provider work.

For a supported memory statement, the host returns a structured `FoundationInteractionRunResult` containing the memory-admission outcome and no response object. No Investigation, ModelInvocation, CompanionOutput, presentation attempt, or presented Timeline event is required.

For a supported world question, the result contains the existing checked response object.

Unsupported high-level input remains canonical Timeline history but fails with `INTERACTION_PURPOSE_UNSUPPORTED` before provider work. The host does not send unsupported input to a model to guess intent.

Exact replay of a memory-only transport event reuses the same admitted input and Claim/Evidence state without provider calls. Exact replay of a completed checked interaction reuses the completed response without duplicate acquisition, generation, adoption, presentation dispatch, or Timeline presentation.

See [F4 Interaction Purpose Gate](F4_INTERACTION_PURPOSE_GATE.md), [F4 Trusted First-Party Ingress](F4_FIRST_PARTY_INGRESS.md), and [F4 First-Party Presentation Acceptance](F4_FIRST_PARTY_PRESENTATION.md).

### Content-free recovery diagnostic

```text
alsoul-host --config ./host.json diagnose \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id>
```

Diagnostics describe the checked-response recovery state and next safe operation without returning counterpart text, captured source bodies, generated prose, or credentials. A memory-only interaction does not need to manufacture checked-response state merely to be diagnosable as successful by the high-level caller.

### Model contract probe

```text
alsoul-host --config ./host.json probe-model-contract
```

This performs a synthetic provider-contract check and creates no CompanionPerson cognition, Timeline, memory, or presentation state.

### Lower-level checked-response execution/recovery

```text
alsoul-host --config ./host.json respond \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id> \
  --surface-binding-id <surface-binding-id> \
  --channel-binding-id <channel-binding-id>
```

`respond` remains the lower-level primitive for an interaction already selected for the checked world-question path. It is not a general intent router and does not reinterpret the input.

```text
interact = select among the bounded implemented F4 semantic paths
respond  = execute/resume the already-selected checked response path
```

After a known complete process-loss boundary, the checked response path may use `--after-process-loss` so the existing provider-recovery coordinator reconciles unresolved attempts before any retry decision.

## First-party presentation acceptance

Presentation remains relevant only when a CompanionOutput exists. The host does not treat adoption or socket write as presentation. A configured first-party sink must positively accept the exact adopted output under a stable semantic presentation key before `COMPANION_PRESENTED_OUTPUT` is committed.

```text
same presentation key + same content
    → same logical acceptance

same presentation key + different content
    → conflict
```

Memory-only interactions never cross this boundary because they create no CompanionOutput.

## Presentation recovery

For a checked response:

```text
CompanionOutput exists
↓
sink accepts stable key
↓
connection lost before receipt reaches host
↓
no presented Timeline event yet
↓
new process retries same key
↓
sink returns same logical acceptance
↓
commit one COMPANION_PRESENTED_OUTPUT
```

This preserves one semantic presentation across multiple transport attempts.

## Administration and bootstrap separation

The host contains no schema-initialization, migration, or foundation-bootstrap command.

```text
alsoul-admin initialize-store / migrate-store
        ≠
alsoul-admin bootstrap-foundation
        ≠
alsoul-host trusted ingress
        ≠
alsoul-host high-level interaction
        ≠
alsoul-host checked-response recovery
```

Missing Person/Counterpart/Relationship roots during ordinary runtime are hard failures rather than implicit bootstrap triggers.

## Output contract

Successful commands emit one compact JSON object to stdout. Failures emit one JSON error object to stderr with a non-zero exit code. Tracebacks are not emitted by default.

`interact` keeps ingress and semantic interaction results distinct:

```text
ingress = what canonical input was admitted
interaction = which bounded semantic path ran and what durable result it produced
```

For memory statements, `interaction.memory_admission` is populated while `interaction.response` is null. For checked questions, `interaction.response` is populated. Process-control output still does not return user-facing response prose from the canonical response path.

## Process-level acceptance

The acceptance suite now proves both high-level branches.

Memory-only interaction with unreachable providers:

```text
trusted memory statement
↓
canonical input
↓
MEMORY_STATEMENT
↓
Evidence + Claim admission
↓
process exits
↓
replay same transport event
↓
same input and memory
↓
world/model/presentation calls remain zero
```

Unsupported input likewise proves canonical ingress can succeed while the high-level purpose gate stops before Investigation/provider state.

The existing checked process acceptance still proves separate-process recovery through HTTPS world acquisition, model generation, presentation acceptance, and exact replay without duplicate work. The uncertain-presentation acceptance case remains unchanged.

A route-mismatch regression separately proves that a canonical input cannot be continued under a different relationship, surface binding, or channel binding.

## Deliberate exclusions

This checkpoint does not add:

- schema initialization, migration, or bootstrap inside `alsoul-host`;
- public network authentication;
- automatic counterpart or relationship creation;
- model-based identity or purpose resolution;
- general conversational routing;
- mixed memory-and-question utterances;
- read/heard/understood receipts;
- effectful external Actions;
- durable delegated tasks;
- schedules/proactivity;
- multi-channel fallback; or
- rich embodiment.

The host remains a narrow executable boundary for one durable companion: trusted input is canonical first, bounded purpose is selected without model authority, memory-only work can terminate honestly without a fabricated response, and checked response work preserves the existing world/cognition/presentation/recovery contracts.
