# F5.A Personal Calendar Acquisition Increment

**Status:** implementation increment  
**Scope:** coherent bounded personal-calendar acquisition through minimized `WorldResult` admission

This increment extends the landed F5.A authority/time foundation through the first real personal-calendar acquisition boundary. It remains subordinate to `F5_EXECUTABLE_CHECKPOINT.md` and does not close F5.A.

The executable path added here is:

```text
prepared personal-calendar Observation
↓
trusted read capability contract + qualified adapter
↓
current per-page authority fence
↓
bounded provider page transport
↓
stable coherent snapshot / cursor validation
↓
trusted occurrence/time normalization
↓
field-level minimization
↓
complete canonical WorldSourceCapture
↓
EvidenceItem
↓
current-state WorldResult
```

The increment deliberately stops before personal-calendar `ContextProjection`, recovery freshness reuse, model-egress authority, structured schedule generation/adoption, first-presentation disclosure authority, and presentation reconciliation.

## Executable constraints

The first acquisition implementation supports only a trusted contract with:

- semantic operation `calendar.events.read` and effect class `READ_ONLY`;
- exactly one selected calendar resource/window inherited from the prepared Observation;
- opaque bounded pagination;
- one stable provider snapshot reference across the whole traversal;
- concrete authoritative occurrences rather than local recurrence expansion;
- raw provider material minimized ephemerally to the explicit normalized event allowlist before host persistence/telemetry;
- finite page, per-page event, total-event, and title bounds.

Every page transport is preceded by a fresh current authority fence. Pagination cannot create another semantic Observation. Permission or other mutable authority reduction between pages blocks the next provider transport.

A terminal cursor is not sufficient by itself. Canonical admission requires one stable snapshot, internally consistent snapshot time when present, no provider result-cap signal, no cursor cycle, no duplicate occurrence identity, deterministic trusted time semantics, and a terminal page within the trusted page bound.

The host rechecks canonical day membership even after provider filtering. Cancelled occurrences are excluded. All-day occurrences must carry explicit exclusive-end dates whose exact instants reproduce under the selected calendar timezone/rules contract.

Only normalized schedule truth is persisted. Raw page cursors are represented only by digests in structural page lineage. Credential secrets, raw provider payloads, descriptions, attendees, organizer data, conferencing data, attachments, reminders, private notes, locations, and unrelated provider metadata are outside canonical capture.

Freshness is anchored to trusted provider `snapshot_as_of` when available; otherwise it remains conservatively anchored to the Observation's pre-transport `acquisition_started_at`. Page completion or capture commit never advances freshness.

Partial, incoherent, capped, revoked, or otherwise invalid traversals do not create `WorldSourceCapture`, `EvidenceItem`, or `WorldResult`, and calendar content does not create personal-memory claims.
