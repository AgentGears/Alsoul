# F5.B calendar action authority increment

This increment begins executable F5.B with one bounded calendar mutation intent: `calendar.event.create`. It deliberately stops before approval presentation, Approval admission, external mutation dispatch, ExecutionAttempt fencing, provider correlation, Effect confirmation, and `UNKNOWN_EFFECT` reconciliation.

The first write grammar is exact and uses explicit offset-aware timestamps. The canonical counterpart input is the semantic source of the Action; callers cannot supply alternate title or time fields beside the canonical interaction. The original timestamp representations and their normalized instants are both pinned into one immutable Action together with the selected PersonalResourceBinding, capability contract/version, source interaction, and Action digest.

Write authority is distinct from F5.A read authority. A read Permission cannot authorize `calendar.event.create`. F5.B therefore introduces a separate append-only calendar-create policy and write-Permission lineage bound to the holder CompanionPerson, counterpart, relationship, selected PersonalResourceBinding, exact capability contract, WRITE operation class, trusted first-party grant event, grant policy/version, and revocable current state.

Action admission re-evaluates current relationship state, current resource-binding state, current calendar-create policy, and current write Permission. Those mutable authority heads and the originating Timeline frontier are compare-and-swap fenced before the immutable Action is committed. The Action retains the exact revisions that authorized its preparation as historical provenance; those revisions do not become dispatch authority for a future mutation attempt.

The first slice still permits exactly one active calendar resource per relationship. Floating local times, timezone inference, recurrence, attendees, conferencing, reminders, edits, deletes, free-form scheduling, and any direct model/tool execution authority remain outside this increment.

A later F5.B increment must add faithful approval-presentation provenance and operation-specific Approval for the exact Action before any effectful dispatch can become eligible. Subsequent increments must then add per-Action dispatch serialization, durable dispatch-start fencing, exact adapter/correlation pins, minimized provider evidence, terminal effect truth, and `UNKNOWN_EFFECT` reconciliation without blind retry.
