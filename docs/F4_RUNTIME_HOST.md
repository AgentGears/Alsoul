# F4 Runtime Host

**Status:** Implemented foundation checkpoint

The F4 configured reactive slice has a narrow process-facing host. The host turns the converged persistence, recovery, provider, trusted first-party ingress, presentation-acceptance, and response boundaries into an executable process without creating a second source of semantic authority.

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
        └── configured reactive execution
                ├── world acquisition
                ├── model generation
                └── first-party presentation acceptance
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
CompanionOutput ≠ presentation attempt ≠ sink acceptance ≠ Timeline presentation
presented ≠ read/heard/understood
bootstrap administration ≠ ordinary runtime
```

## Host configuration

The host reads one strict JSON document. Unknown fields fail closed. Relative filesystem paths are resolved relative to the configuration file.

Configuration version 2 requires an explicit first-party presentation endpoint in addition to the world and model routes:

```json
{
  "host_config_version": 2,
  "database": {
    "path": "./alsoul.db"
  },
  "world": {
    "locator": "https://world.example.invalid/requirements",
    "timeout_seconds": 10
  },
  "model": {
    "endpoint": "https://model.example.invalid/generate",
    "provider_binding_ref": "primary-model-route",
    "model_ref": "model-v1",
    "timeout_seconds": 30
  },
  "presentation": {
    "endpoint": "https://surface.example.invalid/present",
    "timeout_seconds": 10
  }
}
```

HTTPS trust remains a process/host infrastructure concern and uses the platform TLS trust configuration. It is not evidence, identity, permission, or canonical companion state.

The model authorization token is intentionally absent from the file. If required, it is supplied only through:

```text
ALSOUL_MODEL_AUTHORIZATION_TOKEN
```

The host does not persist that value, render it into provider context, include it in semantic payloads, or return it from diagnostics.

The presentation endpoint is likewise route configuration rather than authority or identity. Its availability does not imply permission to contact a counterpart beyond the bounded first-party reactive response already being executed.

## Readiness

`ready` performs local startup checks only:

```text
configuration parses
        ↓
database file already exists
        ↓
database is readable
        ↓
required F4 tables exist
        ↓
required F4 columns exist
        ↓
foreign-key enforcement is active
        ↓
READY
```

It performs no world, model, or presentation I/O. Provider contract verification is a separate operation so local process readiness cannot silently become a remote dependency check.

A missing database fails closed and is not created as a side effect of readiness. A structurally compatible but identity-empty database can pass this readiness check because identity bootstrap is a separate administration concern; ingress will still fail closed until the required bindings exist.

## Commands

### Readiness

```text
alsoul-host --config ./host.json ready
```

### Trusted first-party input admission

```text
cat envelope.json | alsoul-host --config ./host.json ingest
```

`ingest` resolves pre-existing identity, relationship, surface, and channel bindings and commits exactly one canonical `COUNTERPART_INPUT` event. The process caller must already have authenticated the external subject represented by the envelope.

The model is not involved in identity resolution. Missing bindings fail closed and never trigger bootstrap.

### One-shot first-party interaction

```text
cat envelope.json | alsoul-host --config ./host.json interact
```

`interact` composes trusted ingress with the response coordinator and first-party presentation acceptance boundary:

```text
trusted transport assertion
↓
COUNTERPART_INPUT committed
↓
Investigation / Observation / WorldResult
↓
ContextProjection
↓
ModelInvocation / GeneratedOutput
↓
CompanionOutput
↓
first-party presentation attempt
↓
validated sink acceptance
↓
COMPANION_PRESENTED_OUTPUT
```

Exact replay of the same logical transport event reuses the admitted input. If its semantic response is already presented, the replay does not repeat world acquisition, generation, adoption, sink dispatch, or Timeline presentation.

See [F4 Trusted First-Party Ingress](F4_FIRST_PARTY_INGRESS.md) for the envelope, identity-resolution, and ingress-idempotency contracts. See [F4 First-Party Presentation Acceptance](F4_FIRST_PARTY_PRESENTATION.md) for the sink acceptance and presentation-recovery contract.

### Content-free recovery diagnostic

```text
alsoul-host --config ./host.json diagnose \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id>
```

The diagnostic reports semantic recovery stage, durable attempt identifiers, blockers, and the next safe operation. It does not return counterpart input text, captured source bodies, generated prose, or credentials.

### Model contract probe

```text
alsoul-host --config ./host.json probe-model-contract
```

This performs a synthetic provider-contract check. It does not create `ModelInvocation`, `GeneratedOutput`, Timeline, memory, presentation, or other CompanionPerson cognition state.

### Resume an already-admitted response

```text
alsoul-host --config ./host.json respond \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id> \
  --surface-binding-id <surface-binding-id> \
  --channel-binding-id <channel-binding-id>
```

`respond` remains available as the lower-level recovery/control command. It consumes an already-admitted `COUNTERPART_INPUT` event and therefore preserves the invariant that current input enters canonical Timeline history before cognition begins.

After a known complete process-loss boundary, `respond` or `interact` may add:

```text
--after-process-loss
```

That path uses the existing provider-recovery coordinator before deciding whether provider execution may safely resume.

## First-party presentation acceptance

The host does not treat an internal adoption or a socket write as presentation. The configured first-party sink must positively accept the exact adopted output under a stable semantic presentation key.

The request carries:

```text
presentation_key
companion_output_id
surface_binding_id
channel_binding_id
content_text
content_digest
```

The sink returns an acceptance receipt whose key and content digest must exactly match the request.

Only after receipt validation may the response coordinator commit `COMPANION_PRESENTED_OUTPUT` to the canonical Timeline.

The sink contract is idempotent:

```text
same presentation key + same content
    → same logical acceptance

same presentation key + different content
    → conflict
```

This makes recovery safe if the sink accepted the output but the process lost the response before the Timeline commit.

## Presentation recovery

The important uncertain path is:

```text
CompanionOutput exists
↓
sink accepts stable key K1
↓
connection disappears before receipt reaches host
↓
host reports unknown presentation outcome
↓
no COMPANION_PRESENTED_OUTPUT exists yet
↓
new process recovers same CompanionOutput
↓
retry K1 with exact content
↓
sink returns existing logical acceptance
↓
commit one COMPANION_PRESENTED_OUTPUT
```

The network may contain two transport attempts. Alsoul still has one logical first-party presentation and one canonical Timeline presentation event.

If the Timeline event already exists, recovery returns the existing completed response and does not redispatch to the presentation sink.

## Administration and bootstrap separation

The runtime host intentionally has no schema-initialization, migration, or bootstrap command. Those operations live in the separate `alsoul-admin` process boundary:

```text
alsoul-admin initialize-store / migrate-store
        ≠
alsoul-admin bootstrap-foundation
        ≠
alsoul-host trusted ingress
        ≠
alsoul-host ordinary response execution / recovery
```

`alsoul-admin bootstrap-foundation` invokes the explicit `FoundationBootstrapper` boundary with an empty-store fence. If Person, CounterpartPerson, RelationshipState, or their foundation bindings are missing during ordinary runtime, `alsoul-host` fails rather than calling administration or manufacturing replacement identity.

See [F4 Administration and First-Run Bootstrap](F4_ADMINISTRATION.md) for the installation, migration, bootstrap, and administration-status contract.

## TLS transport

The host uses HTTPS-only configured runtime contracts and the process platform's TLS trust configuration. Cross-origin model and presentation resolution is rejected so route semantics cannot silently move to another origin.

## Output contract

Successful host commands emit one compact JSON object to standard output. Failures emit one JSON error object to standard error with a non-zero exit code. The host does not emit traceback state by default.

Process-control responses contain durable semantic identifiers rather than counterpart input or user-facing output prose. `interact` returns separate `ingress` and `response` objects so transport admission and cognition/presentation remain distinguishable.

An unknown presentation transport outcome is reported as an adapter-outcome uncertainty and does not falsely report a `presented_event_id`.

## Process-level acceptance

The acceptance suite launches the host in separate Python processes against:

- a file-backed F4 database;
- a local HTTPS world endpoint;
- a local HTTPS model endpoint;
- a local HTTPS first-party presentation endpoint;
- a process-scoped test trust root;
- an environment-only model authorization token.

The normal process test proves:

```text
ready
↓
ingest trusted input
↓
process exits
↓
replay ingest → same InteractionEvent
↓
diagnose INPUT_ADMITTED
↓
synthetic model-contract probe
↓
interact same transport event
↓
recover admitted input
↓
HTTPS world acquisition
↓
WorldResult admission
↓
ContextProjection
↓
HTTPS model generation
↓
CompanionOutput adoption
↓
HTTPS presentation acceptance
↓
COMPANION_PRESENTED_OUTPUT
↓
replay interact → same completed response, no duplicate provider or sink work
```

A second process test forces the presentation sink to accept the output and then close the connection before returning its receipt. It verifies:

```text
first attempt
    sink logical acceptance = 1
    presented Timeline events = 0

retry in a new process
    same semantic presentation key
    sink logical acceptance still = 1
    presented Timeline events = 1
    world/model work not repeated
```

A separate administration/process test starts from a fresh store, explicitly initializes and bootstraps it through `alsoul-admin`, and proves that an identity-empty but schema-compatible runtime host does not create missing bindings when ingress fails.

The tests also verify that provider credentials and counterpart input are not echoed through process-control output.

## Deliberate exclusions

This checkpoint does not add:

- schema initialization, migration, or bootstrap inside `alsoul-host`;
- public network authentication;
- automatic counterpart or relationship creation;
- model-based identity resolution;
- read/heard/understood receipts;
- effectful external Actions;
- durable delegated tasks;
- schedules or proactivity;
- multi-channel fallback;
- rich embodiment.

The purpose remains narrow: execute one trusted first-party F4 interaction end to end while preserving canonical identity, history, evidence, cognition, adoption, actual first-party presentation acceptance, and recovery boundaries while keeping first-run administration outside the runtime host.
