# F5.B Calendar Terminal No-Effect and Retry Increment

This increment advances an unresolved `calendar.event.create` attempt from conservative `UNKNOWN_EFFECT` to authoritative terminal `CONFIRMED_NO_EFFECT`, then permits at most one explicit retry claim under fresh current mutation authority.

## Terminal negative truth

Ordinary reconciliation absence remains non-terminal. `NOT_FOUND`, rejection, malformed responses, transport uncertainty, or any observation that cannot prove transport terminality leaves the Action in `UNKNOWN_EFFECT` and keeps the per-Action dispatch guard locked.

`CONFIRMED_NO_EFFECT` requires a trusted capability-specific negative-confirmation contract pinned into the original mutation dispatch fence. The admitted evidence must mechanically establish all of the following for the exact fenced `ExecutionAttempt`:

```text
Action correlation matches the immutable Action
AND intended Action-correlated effect is authoritatively absent
AND provider operation status is TERMINAL_NOT_APPLIED
AND terminality scope is EXACT_EXECUTION_ATTEMPT
AND the provider contract guarantees no delayed application after terminal status
AND durable proof references identify both terminality and authoritative absence
AND the exact attempt acquired the one-shot mutation dispatch claim
```

The negative-confirmation provider call is itself a fresh `calendar.events.read` operation. Before transport, the host reuses the current-authorized reconciliation fence and therefore re-evaluates current RelationshipState, selected calendar resource, read Permission, read policy, CredentialBinding, provider scope, and adapter/correlation contract qualification.

The no-effect operation also acquires a durable operation claim before provider transport. Concurrent reuse of one operation id cannot issue duplicate terminal-negative provider calls. A process loss in an incomplete claimed operation requires an explicit new recovery operation; it does not manufacture a result.

## Atomic no-effect admission

Sufficient terminal proof is committed atomically as:

```text
PersonalCalendarCreateNoEffectEvidence
    SUPPORTS
PersonalCalendarCreateNoEffect(status = CONFIRMED_NO_EFFECT)
```

In the same transaction, the exact owning `ExecutionAttempt` and per-Action dispatch guard advance from `UNKNOWN_EFFECT` to `CONFIRMED_NO_EFFECT`. Positive effect evidence or an existing confirmed Effect blocks negative admission.

The reconciliation probe is completed as an authoritative absence observation, but the stronger terminality proof lives in the dedicated no-effect evidence record. This preserves the distinction between ordinary read absence and retry-authorizing terminal negative truth.

## Explicit retry consumption

`CONFIRMED_NO_EFFECT` does not make generic Action preparation available. The ordinary preparation path remains locked. Retry requires a separate `PreparePersonalCalendarCreateRetryAttempt` transition.

That transition atomically:

1. verifies the exact prior attempt still owns the Action guard in `CONFIRMED_NO_EFFECT`;
2. verifies the durable no-effect record, SUPPORTS linkage, exact-attempt negative evidence, correlation, and trusted terminal-negative contract;
3. re-evaluates current mutation authority, including current RelationshipState, resource, write policy, write Permission, Approval, credential/provider scope, Action constraints, and concrete execution binding;
4. requires the new execution binding to retain the trusted terminal-negative contract;
5. creates exactly one next-generation `ExecutionAttempt` in `PREPARED` state using the same Action-specific external correlation identity;
6. records a unique durable retry claim consuming the prior no-effect authority; and
7. advances the per-Action guard to the new attempt in the same transaction.

A second worker cannot consume the same confirmed no-effect state. Revocation or expiry before retry prevents the new attempt from being created.

## Pinned negative semantics

The original execution fence now recognizes two explicit negative-confirmation semantics:

- `CALENDAR_CREATE_NEGATIVE_CONFIRMATION_UNSUPPORTED_V1`, preserving the prior conservative behavior; and
- `CALENDAR_CREATE_NEGATIVE_CONFIRMATION_V1`, whose trusted contract requires exact-attempt terminal non-application, authoritative Action-correlated absence, prohibition of delayed application after terminal status, and safe reuse of the Action correlation identity only after terminal proof.

An old fence pinned to the unsupported contract cannot later be reinterpreted by installing a stronger adapter. Effect-relevant semantics remain those committed at the dispatch fence.

## Explicit boundary

This increment implements authoritative terminal negative truth and one-shot retry consumption. It does not yet implement mutation-completion cognition, `CalendarMutationResultPlanV1`, deterministic strong-completion rendering, or presentation. Those remain subsequent F5.B work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
