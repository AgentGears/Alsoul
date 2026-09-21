# F5 Mutation Wire Closure Increment

**Status:** implementation evidence

This bounded increment closes the remaining provider-wire evidence gap for the first F5.B calendar-create slice. It does not broaden the semantic capability surface.

## Boundary

The existing mutation service already commits the Action-specific dispatch fence and one-shot durable dispatch claim before provider transport. The new concrete HTTPS adapter proves the next boundary mechanically:

```text
canonical Action / ExecutionAttempt
        ↓
trusted minimized adapter request
        ↓
resolve credential secret from non-secret reference inside adapter
        ↓
construct exact provider-wire allowlist
        ↓
one dedicated HTTPS POST, no redirect, no internal retry
        ↓
strict minimized response normalization
        ↓
existing durable Effect-evidence boundary
```

The provider-wire body contains only:

```text
schema_version
operation = calendar.event.create
resource_ref
summary
start_at
end_at
correlation_key
```

Host-only Action and ExecutionAttempt identifiers, Permission/Approval provenance, capability-policy state, adapter metadata, credential references, and credential material do not enter that body.

The credential secret is resolved only immediately before the dedicated transport call. The dedicated transport does not expose arbitrary headers, tracing context, retry configuration, or generic middleware hooks. It constructs the fixed authorization/content headers internally, follows no redirects, performs one request, and returns only a bounded response to the adapter. Transport ambiguity becomes `AdapterOutcomeUnknown`; it never triggers an adapter-local mutation retry.

Successful response material must match one exact allowlist before a `PersonalCalendarCreateMutationResponse` can cross back into the semantic service. Extra provider fields are rejected rather than persisted or promoted as evidence.

## Recovery and durability

This increment does not add a raw outbound request queue or transport cache. Durable mutation state remains the existing opaque canonical Action/ExecutionAttempt/fence/dispatch references and minimized Effect evidence. A process restart therefore reconstructs mutation state from canonical records rather than a persisted ready-to-send request.

Credential rotation remains explicit. A prepared attempt pinned to a credential that is later revoked cannot silently substitute a replacement credential at fence time. The stale attempt must release before a new generation can be prepared with the replacement binding; the Action correlation remains stable and Person/Relationship identity remains unchanged.

## Executable evidence

`tests/test_f5b_calendar_mutation_wire_adapter.py` proves the exact wire allowlist, ephemeral secret boundary, strict response allowlist, same-origin requirement, durable redaction, and one-shot/no-internal-retry behavior.

`tests/test_f5_closure_credential_rotation.py` proves explicit credential rotation, no silent credential substitution into a prepared attempt, stable Action correlation across the new attempt generation, and unchanged Relationship identity.

The full F5 closure decision remains governed by `docs/F5_EXECUTABLE_CHECKPOINT.md` and requires exact-head Foundation CI plus review of the complete F5.A, F5.B, and F5 closure bars.
