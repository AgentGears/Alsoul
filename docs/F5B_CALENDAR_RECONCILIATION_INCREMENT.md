# F5.B Calendar Mutation Reconciliation Increment

This increment advances an unresolved `calendar.event.create` attempt from durable `UNKNOWN_EFFECT` into a separately authorized read-side reconciliation path.

## Implemented boundary

Reconciliation is observation, not mutation retry. An unresolved create attempt retains the per-Action dispatch lock. Before every provider reconciliation lookup, the host independently re-evaluates current calendar-read authority for the exact Action resource:

```text
current RelationshipState is ACTIVE
AND selected PersonalResourceBinding is the unique ACTIVE calendar for the relationship
AND current trusted calendar.events.read Permission is ACTIVE, unexpired, provenance-valid, and resource-matched
AND current personal-calendar read policy ALLOWs the exact resource and capability version
AND current CredentialBinding is ACTIVE and has the required provider read scope
AND reconciliation adapter is qualified for the trusted read capability and Action-correlation contracts
AND the unresolved ExecutionAttempt still owns the Action guard in UNKNOWN_EFFECT
```

The mutable relationship, resource, Permission, credential, and read-policy heads are compare-and-swap fenced in the same transaction that creates the durable reconciliation-probe authority record. Only after that fence commits may the provider read transport observe the request.

The provider request is minimized to the selected external system/resource, the durable Action correlation identity, the exact reconciliation fence/probe identifiers, the trusted correlation contract version, and ephemeral credential secret reference. It does not resend the mutation title/time payload merely to recover effect truth.

## Reconciliation outcomes

A qualified reconciliation adapter may return only:

```text
FOUND     → minimized Action-correlated effect observation
NOT_FOUND → no effect material
```

`FOUND` is admitted as durable mutation evidence only after exact correlation validation and mechanical comparison with the immutable Action resource, summary, normalized start, and normalized end.

```text
FOUND + semantic equality
    → MATCHED_EFFECT_EVIDENCE
    → attempt remains UNKNOWN_EFFECT
    → existing confirmed-Effect admission may consume the durable evidence

FOUND + semantic divergence
    → DIVERGENT_EFFECT_EVIDENCE
    → attempt remains UNKNOWN_EFFECT
    → Action remains dispatch-locked

NOT_FOUND
    → UNKNOWN_EFFECT
    → no negative Effect evidence
    → no retry authority
```

An uncorrelated, malformed, rejected, or transport-uncertain reconciliation response cannot become Action-linked effect evidence. The probe is recorded conservatively as unknown.

## Why NOT_FOUND is not CONFIRMED_NO_EFFECT

An ordinary correlation lookup that currently finds no event does not prove that an earlier queued or in-flight create transport can never apply later. Therefore this increment deliberately does not manufacture terminal negative truth from absence.

`CONFIRMED_NO_EFFECT` still requires capability-specific evidence proving both that the intended Action-correlated consequence does not exist and that every transport covered by the exact fenced ExecutionAttempt is terminal and can no longer later apply the Action.

## Recovery and bounds

Reconciliation probes are READ_ONLY and use a finite trusted `max_probes` contract. A new probe generation requires a fresh current-authority gate. Operation replay after a completed probe is idempotent and does not call the provider again.

Process loss after a reconciliation authority fence but before a completed observation may consume another bounded probe generation under newly evaluated current read authority. It never authorizes a second create mutation.

## Explicit boundary

This increment implements positive read-side recovery of durable matched/divergent effect evidence and conservative negative/unknown observations.

It does **not** implement:

- authoritative terminal `CONFIRMED_NO_EFFECT`;
- cancellation/settling or provider terminal-negative proof;
- release or consumption of retry authority after no-effect confirmation;
- mutation-completion model projection or `CalendarMutationResultPlanV1`;
- deterministic strong-completion rendering or presentation.

Those remain subsequent F5.B work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
