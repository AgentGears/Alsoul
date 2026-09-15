# F5.B Calendar Mutation Completion Increment

This increment advances an evidence-backed `calendar.event.create` Effect into mechanically constrained mutation-completion cognition. It does not let model prose become the source of calendar facts.

## Implemented boundary

Only a durable `CONFIRMED_EFFECT` with exact `SUPPORTS` lineage to semantically matched create evidence may produce a mutation-completion ContextProjection. Projection admission revalidates the immutable Action, owning ExecutionAttempt, dispatch fence, selected PersonalResourceBinding, Action correlation, provider-created evidence, and terminal attempt/Action state.

The host then creates one opaque `mutation_completion_ref`. The model-visible context is exactly:

```text
mutation_completion_ref
result_kind = CREATED
rendering_contract_version = CALENDAR_CREATE_RESULT_V1
```

The model does not receive the Action ID, Effect ID, evidence ID, execution-attempt identity, correlation key, provider effect reference, provider receipt, resource identity, title, start, end, Permission, Approval, CredentialBinding, or other calendar facts.

## Structured result plan

Model generation uses an explicit current ACTIVE route and compare-and-swap fences that route before transport. The accepted `CalendarMutationResultPlanV1` shape contains only the same opaque completion reference and fixed result/rendering identifiers. Extra fields, factual overrides, stale references, cross-completion references, wrong result kinds, and wrong rendering contracts fail closed.

A successful structured plan is durably tied to its exact projection, Action, and Effect. A failed model invocation may be retried through a fresh invocation. An unresolved model outcome requires recovery and cannot be silently redispatched.

## Deterministic adoption

Before CompanionOutput adoption, the host revalidates:

```text
CONFIRMED_EFFECT
AND exact immutable Action
AND exact ExecutionAttempt and dispatch fence
AND exact Action correlation
AND exact SUPPORTS edge
AND semantically matched provider-created evidence
AND exact resource/title/start/end equality
AND terminal CONFIRMED_EFFECT attempt and Action guard
AND exact mutation-completion projection
AND exact structured result plan
```

Only then does the host deterministically render the factual completion statement from the immutable Action. The model cannot supply or override calendar facts. The adopted semantic payload retains only the opaque completion reference, fixed `CREATED` result kind, and rendering-contract version; private Action/Effect/evidence lineage remains in dedicated durable tables.

There is no free-form completion fallback. A forged, stale, malformed, fact-bearing, or unresolved plan remains unadopted.

## Trust boundary

Strong completion language is downstream of durable evidence-backed Effect truth. Neither provider prose nor model prose can manufacture `CREATED` truth. `CONFIRMED_NO_EFFECT` and `UNKNOWN_EFFECT` cannot enter this completion path.

The model route is authority for model transport only. It is not authority for the calendar mutation and cannot reinterpret historical execution or Effect state.

## Explicit boundary

This increment implements mutation-completion projection, minimized model context, structured result planning, exact-lineage revalidation, deterministic CompanionOutput rendering, and adoption.

It does **not** implement first-party presentation of the adopted mutation result. Presentation remains a subsequent F5.B increment under `docs/F5_EXECUTABLE_CHECKPOINT.md`.
