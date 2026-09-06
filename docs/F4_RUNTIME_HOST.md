# F4 Runtime Host

**Status:** Implemented foundation checkpoint

The F4 configured reactive slice now has a narrow process-facing host. The host exists to turn the already-converged persistence, recovery, provider, and response boundaries into an actual executable process without creating a second source of semantic authority.

## Boundary

```text
process configuration
    +
ephemeral transport secret
    +
pre-existing compatible F4 database
        ↓
alsoul-host
        ↓
ConfiguredFoundationRuntime
        ↓
FoundationResponseCoordinator
        ↓
canonical F4 state transitions
```

The host is deliberately not a bootstrapper, schema creator, conversation-ingress API, task scheduler, or authority service.

Permanent distinctions:

```text
runtime configuration ≠ canonical companion state
runtime configuration ≠ credential
credential ≠ identity
host readiness ≠ provider readiness
operator diagnostic ≠ canonical runtime state
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

It performs no provider I/O. Provider contract verification is a separate operation so local process readiness cannot silently become an external effect or remote dependency check.

A missing database fails closed and is not created as a side effect of readiness.

## Commands

### Readiness

```text
alsoul-host --config ./host.json ready
```

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

### Reactive response

```text
alsoul-host --config ./host.json respond \
  --relationship-id <relationship-id> \
  --current-input-event-id <event-id> \
  --surface-binding-id <surface-binding-id> \
  --channel-binding-id <channel-binding-id>
```

`respond` consumes an already-admitted `COUNTERPART_INPUT` event. It does not create the input event itself. This preserves the existing invariant that current input enters canonical Timeline history before cognition begins.

After a known complete process-loss boundary, the operator may add:

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
ordinary runtime response
```

`FoundationBootstrapper` remains an explicit administration boundary. If Person or Relationship roots are missing, ordinary runtime fails rather than manufacturing replacement identity.

## TLS transport

The host uses the existing HTTPS-only configured runtime contracts and the process platform's TLS trust configuration. Model redirects remain blocked so authorization material is not forwarded across origins.

## Output contract

Successful host commands emit one compact JSON object to standard output. Failures emit one JSON error object to standard error with a non-zero exit code. The host does not emit traceback state by default.

The `respond` result contains durable semantic identifiers rather than conversational content:

```text
presented_event_id
companion_output_id
generated_output_id
context_projection_id
world_result_id
```

This keeps the process-control surface separate from the user-facing presentation surface.

## Process-level acceptance

The acceptance suite now launches the host in a separate Python process against:

- a file-backed F4 database;
- a local HTTPS world endpoint;
- a local HTTPS model endpoint;
- a process-scoped test trust root;
- an environment-only model authorization token.

The process test proves the following sequence across the actual command boundary:

```text
ready
↓
diagnose INPUT_ADMITTED
↓
synthetic model-contract probe
↓
respond
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
```

It also verifies that provider credentials do not appear in process output and that readiness/probe operations do not mutate the reactive semantic path incorrectly.

## Deliberate exclusions

This checkpoint does not add:

- a public bootstrap command;
- schema migration orchestration inside the runtime host;
- new input-ingress semantics;
- effectful external Actions;
- durable delegated tasks;
- schedules or proactivity;
- multi-channel fallback;
- rich embodiment.

The purpose is narrower: make the configured F4 reactive slice executable as a real process while preserving the same semantic authority boundaries already proven in-process.
