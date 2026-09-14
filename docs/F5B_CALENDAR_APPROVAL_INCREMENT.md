# F5.B calendar Approval increment

This increment extends the bounded `calendar.event.create` path through faithful first-party consent presentation and operation-specific Approval for one exact immutable Action. It still stops before mutation dispatch, `ExecutionAttempt`, external correlation, Effect admission, and `UNKNOWN_EFFECT` reconciliation.

The approval surface is derived mechanically from canonical Action state. Callers do not supply alternate title, time, resource, capability, effect class, or consent text. The canonical consent payload includes the exact Action identity/digest, selected PersonalResourceBinding, a trusted target-calendar display identity, title/summary, original explicit-offset start/end representations, normalized start/end instants, `calendar.event.create`, WRITE effect class, and a fixed rendering contract version. Its digest is stored with immutable presentation provenance.

The trusted first-party approval adapter is qualified by a stable sink binding and presentation contract version. It receives a restart-stable semantic presentation key and exact consent payload digest. Sink acceptance is authoritative only when its receipt binds that exact key and digest. An unknown or mismatched presentation outcome does not create trusted approval-presentation provenance. Once an accepted presentation is durable, deterministic replay no longer requires the adapter to remain available.

The accepted presentation records the current relationship Timeline frontier. A later Approval source must be a trusted first-party `COUNTERPART_INPUT` from the Action's bound counterpart on the same surface/channel, must carry the exact bounded first-slice approval response, must occur strictly after the stored presentation frontier, and must still be the current Timeline event. A prior confirmation, hidden Action identifier, arbitrary model field, provider response, or stale interaction cannot mint Approval.

Approval admission mechanically revalidates that the presentation still equals the immutable Action and independently rechecks current RelationshipState, the unique active calendar resource, current calendar-create policy, and the Action's current write Permission. Mutable authority heads and the approving Timeline frontier are compare-and-swap fenced before Approval commits. The immutable Approval retains exact Action/presentation digests, authorized approver, trusted ceremony source, relationship/resource, policy revision/version, write-Permission revision, and grant time. Approval state is append-only and revocable.

A materially different calendar-create request produces a different immutable Action and therefore requires its own faithful approval presentation and Approval. A revoked Approval cannot be replaced for the same Action under this first slice.

The next F5.B increment must add dispatch-time authority and per-Action execution serialization. No provider mutation transport is enabled by this increment.
