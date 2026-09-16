# F5.B calendar mutation runtime increment

This increment composes the already-executable calendar-create boundaries into one bounded two-turn first-party runtime path. It does not create new authority semantics and does not weaken any existing stage boundary.

## Runtime ingress

The interaction-purpose gate recognizes only two new exact grammars:

```text
Add '<title>' to my calendar from <offset-aware start> to <offset-aware end>.
APPROVE CALENDAR ACTION <exact lowercase Action digest>
```

The create request cannot execute a mutation. It selects exactly one current active calendar resource and exactly one current eligible write Permission, prepares the immutable Action, and presents the existing Action-bound approval ceremony. The result is `AWAITING_APPROVAL`.

A later trusted counterpart input may enter execution only when its exact approval challenge resolves to exactly one trusted approval presentation on the same relationship, surface, and channel. The approval service then independently revalidates the presentation and current authority before admitting Approval.

## Execution composition

After exact Approval admission, the coordinator composes the existing trusted stages:

```text
current credential selection
→ PREPARED ExecutionAttempt
→ current-authority dispatch fence + one-shot mutation transport
→ minimized Action-correlated evidence
→ CONFIRMED_EFFECT admission only for semantic-match evidence
→ opaque mutation-completion ContextProjection
→ constrained structured result plan
→ deterministic CompanionOutput adoption
→ current-authorized first-party presentation / content-free presentation recovery
```

The coordinator never grants write Permission, never manufactures Approval, and never treats credential availability as authority.

## Uncertainty boundary

`UNKNOWN_EFFECT` and correlated semantic divergence stop before Effect admission. They therefore cannot generate mutation-completion model output, cannot adopt strong completion language, and cannot enter first-party result presentation. Replaying the same approval interaction consumes durable operation receipts and the existing one-shot mutation claim; it does not resend the provider mutation.

This runtime increment does not convert ordinary absence into `CONFIRMED_NO_EFFECT` and does not perform an automatic create retry. The existing separately authorized reconciliation and terminal no-effect/retry boundaries remain authoritative for those transitions.

## Presentation truth

A confirmed external Effect remains distinct from result presentation. Runtime status preserves that distinction:

```text
PRESENTED             = exact sink generation ACCEPTED and canonical presented Timeline event exists
NOT_PRESENTED         = exact sink generation terminally NOT_ACCEPTED; no presented Timeline event
PRESENTATION_UNKNOWN  = exact sink generation remains uncertain; no presented Timeline event
```

An accepted sink result without canonical Timeline presentation, or a non-accepted/unknown result with a presented Timeline event, fails closed as an inconsistent runtime state. A confirmed Effect is not downgraded merely because its result could not be presented.

## Recovery

Stage operation identities are deterministic from the trusted interaction event and stage. Durable receipts make process replay idempotent. Accepted or uncertain result presentation uses the existing exact-generation content-free status recovery path before any new presentation generation may be sent. Replaying an uncertain presentation does not resend its payload; terminal `NOT_ACCEPTED` may authorize a later presentation generation under the existing current disclosure gate without re-executing the calendar Action.

## Boundary

This increment adds orchestration only. It introduces no schema migration and does not redefine Action, Approval, ExecutionAttempt, Effect, completion, or presentation contracts. The next step is an explicit F5.B/F5 closure audit against `docs/F5_EXECUTABLE_CHECKPOINT.md`; any uncovered acceptance gap remains a separate bounded implementation task rather than being silently widened into this runtime coordinator.
