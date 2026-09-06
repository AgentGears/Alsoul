# F4 Runtime Host

**Status:** Implemented foundation checkpoint

The F4 configured reactive slice has a narrow process-facing host. The host turns the converged persistence, recovery, provider, trusted first-party ingress, and response boundaries into an executable process without creating a second source of semantic authority.

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
bootstrap administration ≠ ordinary runtime
```

## Host configuration

The host reads one strict JSON document. Unknown fields fail closed. Relative filesystem paths are resolved relative to the configuration file.

```json
{
  "host_config_version": 1,
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
  }
}
```

HTTPS trust remains a process/host infrastructure concern and uses the platform TLS trust configuration. It is not evidence, identity, permission, or canonical companion state.

The model authorization token is intentionally absent from the file. If required, it is supplied only through:

```text
ALSOUL_MODEL_AUTHORIZATION_TOKEN
```

The host does not persist that value, render it into provider context, include it in semantic payloads, or return it from diagnostics.

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

It performs no provider I/O. Provider contract verification is a separate operation so local process readiness cannot silently become a remote dependency check.

A missing database fails closed and is not created as a side effect of readiness.

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

`interact` composes trusted ingress with the existing response coordinator:

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
COMPANION_PRESENTED_OUTPUT
```

Exact replay of the same logical transport event reuses the admitted input. If its semantic response is already presented, the replay does not repeat world acquisition, generation, adoption, or presentation.

See [F4 Trusted First-Party Ingress](F4_FIRST_PARTY_INGRESS.md) for the envelope, identity-resolution, and idempotency contracts.

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

This performs a synthetic provider-contract check. It does not create `ModelInvocation`, `GeneratedOutput`, Timeline, memory, or other CompanionPerson cognition state.

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

## Bootstrap separation

The host intentionally has no `bootstrap` command.

```text
schema migration / creation
        ≠
foundation identity bootstrap
        ≠
trusted ingress
        ≠
ordinary response execution
```

`FoundationBootstrapper` remains an explicit administration boundary. If Person or Relationship roots are missing, ordinary runtime and ingress fail rather than manufacturing replacement identity.

## TLS transport

The host uses the existing HTTPS-only configured runtime contracts and the process platform's TLS trust configuration. Model redirects remain blocked so authorization material is not forwarded across origins.

## Output contract

Successful host commands emit one compact JSON object to standard output. Failures emit one JSON error object to standard error with a non-zero exit code. The host does not emit traceback state by default.

Process-control responses contain durable semantic identifiers rather than counterpart input or user-facing output prose. `interact` returns separate `ingress` and `response` objects so transport admission and cognition/presentation remain distinguishable.

## Process-level acceptance

The acceptance suite launches the host in separate Python processes against:

- a file-backed F4 database;
- a local HTTPS world endpoint;
- a local HTTPS model endpoint;
- a process-scoped test trust root;
- an environment-only model authorization token.

The process test now proves:

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
COMPANION_PRESENTED_OUTPUT
↓
replay interact → same completed response, no duplicate provider work
```

It also verifies that provider credentials and counterpart input are not echoed through process-control output.

## Deliberate exclusions

This checkpoint does not add:

- a public bootstrap command;
- schema migration orchestration inside the runtime host;
- public network authentication;
- automatic counterpart or relationship creation;
- model-based identity resolution;
- effectful external Actions;
- durable delegated tasks;
- schedules or proactivity;
- multi-channel fallback;
- rich embodiment.

The purpose remains narrow: execute one trusted first-party F4 interaction end to end while preserving canonical identity, history, evidence, cognition, adoption, presentation, and recovery boundaries.
