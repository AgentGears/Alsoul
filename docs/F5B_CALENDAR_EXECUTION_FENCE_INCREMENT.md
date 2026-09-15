# F5.B Calendar Execution-Fence Increment

This increment advances the executable `calendar.event.create` path from immutable Action plus current operation-specific Approval to the last durable boundary before provider mutation transport.

## Implemented boundary

One immutable Action may have at most one current dispatch-eligible or may-have-dispatched `ExecutionAttempt`. Preparing an attempt atomically claims the Action guard and durably establishes the Action-specific external correlation key before any future provider request can exist. The key is derived from the Alsoul Action identity under a fixed correlation contract, not from semantic payload equality.

A PREPARED attempt does not imply transport. It may be abandoned only while no dispatch fence exists, after which a later attempt receives a new generation and must pass current authority again.

Before `DISPATCH_FENCED` commits, the service independently re-evaluates the current relationship, selected resource, calendar-create policy, write Permission, exact Action Approval and faithful approval presentation, authorized counterpart, Action constraints, CredentialBinding, provider scope, and trusted execution binding. The same transaction then pins the exact relationship/resource/policy/Permission/Approval/credential revisions together with the concrete adapter, executor, correlation, and negative-confirmation contract versions.

A surviving dispatch fence is conservative uncertainty. Recovery converts `DISPATCH_FENCED` to `UNKNOWN_EFFECT` without consulting later authority or substituting current adapter semantics, and the per-Action guard remains locked.

## Preserved invariants

```text
Action identity != semantic payload equality
Approval != dispatch authority
PREPARED != may-have-dispatched
DISPATCH_FENCED != confirmed provider invocation
DISPATCH_FENCED != Effect
UNKNOWN_EFFECT != permission to retry
provider idempotency != Alsoul-side dispatch serialization
CredentialBinding != Person identity
runtime execution binding != mutation authority
```

Credential secrets are not copied into the execution fence. Durable attempt state retains only the selected credential identity/revision and normalized provider-scope snapshot required to explain the authority decision.

## Explicit boundary

This increment does **not** issue a provider mutation request and does not admit Effect evidence. Provider request minimization, actual transport, `CONFIRMED_EFFECT`, authorized reconciliation probes, terminal `CONFIRMED_NO_EFFECT`, retry consumption, and mutation-completion cognition remain subsequent F5.B work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
