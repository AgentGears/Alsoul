# F5.B Calendar Confirmed-Effect Increment

This increment advances the executable `calendar.event.create` path from durable minimized mutation evidence to terminal positive Effect truth.

## Implemented boundary

A provider response, mutation-dispatch receipt, or `MATCHED_EFFECT_EVIDENCE` transport result is not itself a confirmed Effect. The host admits `CONFIRMED_EFFECT` only from an already-durable `personal_calendar_create_effect_evidence` row that is mechanically revalidated against the exact immutable Action and its fenced ExecutionAttempt.

Admission requires:

```text
same execution_attempt_id / action_id lineage
exact durable dispatch fence exists
exact Action-specific correlation matches the attempt/fence
validation_kind = SEMANTIC_MATCH
provider_status = CREATED
trusted evidence schema version
external system/resource == Action-selected resource
normalized summary == Action summary
normalized start == Action normalized start
normalized end == Action normalized end
required provider proof references are present
attempt still owns the per-Action dispatch guard
attempt/guard remain unresolved as DISPATCH_FENCED or UNKNOWN_EFFECT
```

The semantic proof is rechecked at Effect admission rather than trusting the earlier `SEMANTIC_MATCH` label alone. Tampered, cross-Action, divergent, or uncorrelated evidence cannot become terminal Effect truth.

## Atomic proof ordering and terminalization

The admission transaction creates:

```text
PersonalCalendarCreateEffect(status = CONFIRMED_EFFECT)
+
PersonalCalendarCreateEffectSupport(support_kind = SUPPORTS)
+
ExecutionAttempt state → CONFIRMED_EFFECT
+
per-Action dispatch guard → CONFIRMED_EFFECT
```

in one commit. Therefore no visible confirmed Effect can exist without its required durable SUPPORTS evidence, and the same commit makes the Action terminal for mutation dispatch.

If matched evidence was committed before process loss and the attempt later recovered conservatively to `UNKNOWN_EFFECT`, Effect admission can still consume that durable evidence and terminalize the Action without redispatch.

Repeated admission commands recover the same Effect identity when they name the same evidence lineage. A different evidence lineage cannot silently replace the already admitted Effect.

## Explicit boundary

This increment implements only positive `CONFIRMED_EFFECT` admission from already-durable matched mutation evidence.

It does **not** implement:

- `CONFIRMED_NO_EFFECT`;
- read-side mutation reconciliation;
- retry release/consumption after authoritative no-effect proof;
- mutation-completion model projection or `CalendarMutationResultPlanV1`;
- deterministic strong-completion rendering or presentation.

Those remain subsequent F5.B work under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
