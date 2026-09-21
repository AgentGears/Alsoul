# F5 Exit Audit

**Status:** pending exact-head verification and final review

**Normative basis:** `docs/F5_EXECUTABLE_CHECKPOINT.md`

This audit records independently established executable and review evidence for Foundation 5 without weakening the checkpoint. It is an evidence register, not a mechanism for self-certifying zero defects. F5 closes only when the F5.A acceptance bar, the F5.B acceptance bar, and the F5 closure bar are all supported by independently verified behavior on the exact reviewed head.

The 26 closure-specific controls are an audit overlay used to target residual closure risk. They do not replace, narrow, or stand in for the complete F5.A and F5.B acceptance matrices in `docs/F5_EXECUTABLE_CHECKPOINT.md`; closure requires both the full normative acceptance bars and the closure overlay to be satisfied.

## F5.A evidence

The personal-calendar read tranche is covered by the F5.A exit suites and the underlying authority, acquisition, cognition, presentation, and runtime suites. Together they exercise current relationship/resource/Permission/credential authority; trusted calendar time semantics; bounded complete coherent acquisition; recurrence normalization; field minimization; freshness; model-egress authority and route eligibility; deterministic schedule-plan validation; first-party presentation truth; and restart/recovery behavior.

Primary executable evidence:

- `tests/test_f5a_exit_authority.py`
- `tests/test_f5a_exit_authority_additional.py`
- `tests/test_f5a_exit_page_authority.py`
- `tests/test_f5a_exit_acquisition.py`
- `tests/test_f5a_exit_acquisition_contract.py`
- `tests/test_f5a_exit_cognition.py`
- `tests/test_f5a_exit_cognition_additional.py`
- `tests/test_f5a_exit_presentation.py`
- `tests/test_f5a_exit_presentation_additional.py`
- `tests/test_f5a_exit_presentation_contract.py`
- `tests/test_f5a_current_runtime_calendar.py`
- `tests/test_f5a_current_runtime_recovery.py`
- `tests/test_f5a_current_runtime_uncertain_recovery.py`

## F5.B evidence

The bounded calendar-create tranche keeps Capability, Permission, Approval, Action, ExecutionAttempt, Effect, completion cognition, CompanionOutput, and presentation as distinct states.

Action and authority evidence is covered by:

- `tests/test_f5b_calendar_action_authority.py`
- `tests/test_f5b_calendar_approval_authority.py`
- `tests/test_f5b_calendar_approval_review.py`
- `tests/test_f5b_calendar_approval_review_followup.py`
- `tests/test_f5b_calendar_execution_fence.py`
- `tests/test_f5b_calendar_execution_conflicts.py`

Mutation dispatch, correlation, uncertainty, evidence ordering, and confirmed Effect are covered by:

- `tests/test_f5b_calendar_mutation_transport.py`
- `tests/test_f5b_calendar_mutation_transport_correlation.py`
- `tests/test_f5b_calendar_confirmed_effect.py`
- `tests/test_f5b_calendar_reconciliation.py`
- `tests/test_f5b_calendar_reconciliation_hardening.py`
- `tests/test_f5b_calendar_no_effect_retry.py`

Mutation completion and first-party presentation truth are covered by:

- `tests/test_f5b_calendar_mutation_completion.py`
- `tests/test_f5b_calendar_mutation_completion_integrity.py`
- `tests/test_f5b_calendar_mutation_presentation.py`
- `tests/test_f5b_calendar_mutation_runtime.py`
- `tests/test_f5b_calendar_mutation_configured_runtime.py`

The provider-wire requirements in acceptance items 62–66 are additionally covered by `tests/test_f5b_calendar_mutation_wire_adapter.py`. The concrete provider-neutral HTTPS adapter constructs the provider request from an exact allowlist, resolves credential material only inside the trusted adapter at dispatch, performs one no-redirect/no-internal-retry transport attempt, rejects response material outside the minimized contract before semantic admission, and leaves durable retry/recovery authority in canonical Action/fence/correlation state rather than a raw outbound request copy.

Credential rotation is covered explicitly by `tests/test_f5_closure_credential_rotation.py`: revocation after preparation prevents the stale credential from being silently replaced inside that attempt; a replacement binding requires a new explicit attempt generation, while Action correlation and Person/Relationship identity remain stable.

## Closure review

The executable architecture preserves the required distinctions across both tranches:

```text
Person / Relationship
≠ external account / resource / credential

Capability availability
≠ Permission
≠ Approval

Action
≠ ExecutionAttempt
≠ Effect

provider response
≠ durable Effect evidence
≠ Effect

GeneratedOutput
≠ CompanionOutput
≠ payload dispatch
≠ sink acceptance
```

Read and write authority remain separate. Current authority is re-evaluated at the concrete transport boundaries required by the checkpoint. Mutation uncertainty remains `UNKNOWN_EFFECT` until separately authorized reconciliation resolves it; blind replay is prohibited. `CONFIRMED_NO_EFFECT` requires terminal non-application proof before explicit retry release. Strong completion claims require exact evidence-backed `CONFIRMED_EFFECT`, the opaque mutation-completion projection/result-plan boundary, deterministic adoption validation, and truthful presentation state.

Personal-world material does not become generic durable memory merely because it was observed, and credential secrets remain outside canonical cognition, durable mutation evidence, and model context.

## Exit condition

This document becomes a closed F5 audit only after all of the following are independently established on the exact pull-request head:

1. Foundation CI passes compilation, the complete acceptance suite, and migration round trip.
2. Manual exact-head review finds no unresolved checkpoint or implementation blocker.
3. Pull-request review discussion contains no unresolved blocking finding.
4. The reviewed head remains unchanged through merge.

Until those conditions are satisfied, this audit is evidence-in-progress rather than a closure claim. The audit text alone is never evidence that these conditions passed.
