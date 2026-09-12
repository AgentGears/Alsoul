# F5.A Personal Calendar Presentation Increment

**Status:** implementation increment  
**Scope:** current first-presentation authority and exact-generation sink reconciliation

This increment extends the landed F5.A acquisition/cognition path from an unpresented deterministic personal-calendar `CompanionOutput` through the first accepted first-party presentation. It remains subordinate to `F5_EXECUTABLE_CHECKPOINT.md`.

The executable path added here is:

```text
unpresented personal-calendar CompanionOutput
↓
current presentation-time freshness decision
↓
current disclosure authority for exact first-party route
↓
transactional authority + Timeline dispatch fence
↓
durable PersonalPresentationAttempt generation
↓
payload-bearing first-party transport
↓
ACCEPTED | terminal NOT_ACCEPTED | UNKNOWN
↓
content-free exact-generation reconciliation when needed
↓
exactly one canonical COMPANION_PRESENTED_OUTPUT after accepted sink evidence
```

## Authority boundary

A durable `GeneratedOutput` or `CompanionOutput` is historical cognition, not an indefinitely reusable disclosure token. Immediately before each payload-bearing transport, the host independently requires:

- current freshness from the underlying personal-calendar `freshness_anchor_at` under the current freshness policy;
- active current personal-world relationship authority;
- the same active calendar resource association;
- current trusted read Permission with matching holder/counterpart/relationship/resource provenance;
- current read policy compatibility;
- current personal-data disclosure policy allowing the exact first-party surface/channel route;
- the trusted presentation and status contract versions;
- the originating interaction still at the Timeline frontier for a new first presentation.

Credential usability and provider technical scope are not presentation prerequisites. They matter only if stale state requires a new authorized acquisition.

The mutable heads used by the payload decision are linearized inside the same transaction that commits the presentation attempt/fence. A concurrent authority reduction that wins first prevents payload dispatch.

## Presentation identity

The stable `presentation_key` is the semantic identity of one `CompanionOutput` on one first-party route. It remains unchanged across bounded attempt generations.

Every payload transport also carries:

```text
presentation_attempt_generation
presentation_transport_fence_scope_id
```

Acceptance, terminal-negative evidence, and status lookup must bind all three values. Evidence from another generation cannot satisfy the current attempt.

## Uncertain acceptance

The attempt is durably `UNKNOWN` before the payload transport starts. A lost acknowledgement therefore never means either “definitely undisclosed” or “presented.”

Recovery of `UNKNOWN` uses only the exact-generation content-free status lookup. That request carries no schedule payload and no content digest.

A lookup can establish:

```text
ACCEPTED
NOT_ACCEPTED with authoritative terminal-negative evidence
UNKNOWN
```

`NOT_ACCEPTED` is accepted only under the trusted status contract and requires explicit terminal proof plus a settled-through reference. A transient or point-in-time negative result is represented as `UNKNOWN` instead.

Once `ACCEPTED` is durably established, recovery may append the canonical historical Timeline event without rechecking current disclosure Permission because that append records an already-observed sink acceptance; it does not redisclose the payload.

A later payload transport is allowed only after the immediately prior generation is authoritatively `NOT_ACCEPTED`. It uses a new generation/fence identity, retains the stable semantic `presentation_key`, and re-evaluates current freshness/disclosure authority before sending any payload.

## Fail-closed properties

- Generic foundation presentation remains blocked for personal-calendar lineage.
- Stale output is not sent as an unqualified current answer.
- Disclosure denial does not trigger reacquisition merely to bypass denial.
- Unknown acceptance never authorizes a payload resend.
- Status lookup never carries the personal payload or its digest.
- A mismatched presentation key, generation, fence scope, or status contract is rejected as untrusted evidence.
- Terminal-negative state requires authoritative proof, not absence of acceptance.
- At most one canonical Timeline presentation event is committed for the `CompanionOutput`.
- Later Permission, resource, relationship, disclosure-policy, or freshness changes do not erase an already accepted historical presentation event.
