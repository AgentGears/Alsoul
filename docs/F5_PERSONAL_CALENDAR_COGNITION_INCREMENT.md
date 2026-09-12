# F5.A Personal Calendar Cognition Increment

**Status:** implementation increment  
**Scope:** current-policy projection, exact-route model egress, structured schedule planning, and deterministic CompanionOutput adoption

This increment extends the landed personal-calendar acquisition boundary from minimized `WorldResult` truth through one bounded cognition path. It remains subordinate to `F5_EXECUTABLE_CHECKPOINT.md` and does not close F5.A.

The executable path added here is:

```text
personal-calendar WorldResult
↓
current freshness-policy decision
↓
interaction-bound minimized ContextProjection
↓
current Permission/resource/read-policy/model-egress/route/freshness gate
↓
structured CalendarAnswerPlan proposal
↓
host validation of exact projection/result/date/occurrence coverage
↓
deterministic schedule rendering from immutable projected facts
↓
CompanionOutput adoption
```

First-party presentation, presentation-time freshness/disclosure authority, uncertain sink acceptance, acceptance reconciliation, and any user-visible Timeline append remain subsequent work.

## Projection and recovery rules

A personal-calendar result can be projected only for the exact counterpart interaction that caused its Observation. The originating input must still be the relationship Timeline frontier. Another interaction cannot reuse the result as generic personal context.

Every recovered result is evaluated against the current relationship-scoped freshness policy using its persisted `freshness_anchor_at`. Tightening the policy or allowing time to elapse may make the immutable result ineligible without mutating acquisition history. A separate durable freshness decision is recorded for projection and again for model egress.

The model-facing projection replaces provider occurrence identities with projection-local opaque schedule-item references. It exposes only the bounded schedule fields required for the answer: normalized title, start/end or all-day semantics, requested date/timezone, and source classification. Credential secrets, provider resource identifiers, recurrence mechanics, and acquisition cursor material are not rendered into model context.

## Exact-route model egress

Before every personal-data model transport, the host re-evaluates current:

- personal-world relationship authority;
- selected calendar resource state;
- trusted read Permission state and expiry;
- read policy and Permission provenance compatibility;
- personal-calendar freshness policy;
- model-egress policy;
- exact registered provider/model route state;
- route retention and residency classes;
- originating interaction frontier.

The durable egress decision records the exact revisions and route contract used for that dispatch. A lost or unknown model response does not authorize replay. A later retry requires a new dispatch operation and therefore a new current-policy gate. Egress denial never triggers implicit reacquisition.

## Structured cognition and deterministic adoption

The model does not author final schedule facts or user-visible schedule prose. It may return only a bounded `CALENDAR_ANSWER_PLAN_V1` object containing:

- the exact source ContextProjection ID;
- the exact source WorldResult ID;
- the exact requested date;
- an ordered list of projection-local occurrence references;
- `DAY_SCHEDULE_V1` as the rendering contract;
- optional `NEUTRAL` framing mode.

Unknown fields are rejected, so the plan cannot override titles, times, dates, resources, or occurrence details. Adoption requires every projected occurrence exactly once, with no unknown, duplicate, missing, cross-projection, or cross-result reference. An empty list is valid only when the complete projected result is actually empty.

The host resolves plan references back to immutable projected schedule facts and renders the CompanionOutput deterministically. Calendar titles are quoted as inert data; instruction-like title text cannot become host instructions. The resulting CompanionOutput remains unpresented until the later presentation-authority increment succeeds.
