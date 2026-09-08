# F5 Executable Checkpoint — Personal World + Trust

**Status:** Converged implementation contract; implementation pending  
**Publication:** GitHub-safe  
**Predecessor:** [F4 Exit Audit](F4_EXIT_AUDIT.md)  
**Architecture basis:** Decisions 06.A–06.C, 07.A–07.B, 08.A–08.B, 11.A, 14.A, and 15.A–15.B

F5 begins only after the executable F4 foundation is closed. Its purpose is not to add a broad connector surface. Its purpose is to prove that Alsoul can enter the counterpart's personal digital world under explicit authority while preserving the same Person, epistemic honesty, provenance, recovery, and fail-closed behavior established in F4.

The trust progression is deliberately staged:

```text
public-world observation
↓
selected personal-world read
↓
prepared external action
↓
explicitly approved bounded mutation
↓
effect confirmation / reconciliation
```

Read authority does not imply write authority. Access to one personal resource does not imply access to another. Access to personal data does not make that data durable personal memory.

## Governing invariants

```text
CompanionPerson ≠ external account
CredentialBinding ≠ CounterpartPerson
Credential possession ≠ Permission
Capability availability ≠ Permission
Permission ≠ Approval
read / observe ≠ write / act
personal-world observation ≠ MemoryClaim
WorldSourceCapture ≠ general memory eligibility
Action ≠ ExecutionAttempt ≠ Effect
failed effect ≠ unknown effect
historical access ≠ current authority
provider/tool identity ≠ semantic capability
execution isolation ≠ capability authorization
```

Authority is monotonic narrowing:

```text
Host Capability
∩ AI Capability Policy
∩ Resource Scope
∩ User Permission
∩ operation-specific Approval when required
= maximum authority for this operation
```

No lower layer may manufacture authority that is absent, unreadable, expired, revoked, or denied above it.

## F5 implementation strategy

F5 is split into two executable tranches. The first tranche is read-only and is the immediate implementation target. The second tranche introduces one bounded mutation and closes the Action/Effect loop. F5 is not considered closed until both tranches satisfy their acceptance bars.

```text
F5.A  personal-world observation
F5.B  bounded external action + effect reconciliation
```

This split prevents the first connector from collapsing observation and action semantics into one integration boundary.

# F5.A — Read-only personal calendar observation

## Objective

Answer one bounded current-state calendar question by actually reading one explicitly selected calendar resource under current authority.

The first executable grammar is intentionally narrow and absolute-date based:

```text
"What's on my calendar on YYYY-MM-DD?"
"What do I have on my calendar on YYYY-MM-DD?"
```

Relative-date expressions such as `tomorrow`, natural-language recurrence reasoning, free-form calendar search, email, contacts, files, and cross-resource aggregation remain outside the first slice. Relative dates require a separate trusted timezone contract and must not be inferred from process-local time.

## Semantic path

```text
trusted COUNTERPART_INPUT
↓
bounded PERSONAL_CALENDAR_QUESTION classification
↓
resolve one selected personal calendar resource
↓
evaluate read authority
    calendar.events.read capability available
    AND AI policy permits read
    AND resource is inside declared scope
    AND current user Permission authorizes read
    AND usable CredentialBinding exists
↓
Investigation
↓
Observation
↓
personal-calendar connector read
↓
WorldSourceCapture
↓
EvidenceItem
↓
WorldResult
↓
ContextProjection
↓
ModelInvocation / GeneratedOutput
↓
CompanionOutput adoption
↓
first-party presentation
```

The connector performs acquisition only. It does not decide semantic routing, permission, memory admission, or what the model may see.

## Capability contract

The first semantic capability is:

```text
calendar.events.read
```

This is a provider-independent operation family. Provider API method names, plugin names, transport endpoints, and credential types are adapter details and cannot define authority.

The trusted capability contract must declare at least:

```text
capability_id / semantic operation
contract version
READ effect class
supported resource kind = CALENDAR
request constraints
response semantics
```

A missing or unreadable capability declaration blocks dispatch. The runtime must not infer effect class from a tool/function name.

## Personal resource identity

The selected calendar is represented separately from Person identity and credential identity.

Conceptually:

```text
PersonalResourceBinding {
    personal_resource_binding_id
    counterpart_id
    relationship_id
    resource_kind = CALENDAR
    external_system_ref
    external_resource_ref
    display_label?
    status
}
```

The exact physical representation may differ, but the following must be enforceable:

```text
PersonalResourceBinding ≠ CounterpartPerson
PersonalResourceBinding ≠ CredentialBinding
external principal ≠ CounterpartPerson identity
```

The first slice requires exactly one configured active calendar resource for the relationship. Zero resources fail unavailable. More than one active resource fails ambiguous until an explicit resource selector contract exists.

## Credential binding

A `CredentialBinding` establishes how the trusted host can authenticate to the selected external system. It does not define the user, relationship, permission, or capability.

Credential secrets remain outside canonical cognition and outside persisted provider context. Canonical state may retain a secret reference or binding identifier, never the secret itself.

Credential removal or rebinding must not change `CompanionPerson`, `CounterpartPerson`, `RelationshipState`, canonical Timeline identity, or previously established evidence identity.

## Permission contract

F5.A requires explicit standing read Permission for:

```text
holder = current CompanionPerson
capability = calendar.events.read
resource = selected PersonalResourceBinding
operation class = READ
```

The grant must be current, unrevoked, and within any declared expiry/constraint window before connector dispatch.

The first slice does not require per-interaction Approval for a read because the user is actively asking the read question and the standing Permission is bounded to one selected calendar resource. This does not generalize to writes. A future policy may require read approval without weakening any higher authority layer.

Missing, malformed, unreadable, expired, or revoked Permission fails closed before acquisition.

## Authority provenance for reads

A successful personal-world Observation must retain enough immutable authority provenance to answer:

```text
which semantic capability authorized the read?
which personal resource was read?
which Permission was current?
which CredentialBinding was used?
which user interaction caused the read?
```

The implementation may persist this as an Observation authority relation/snapshot rather than a new general-purpose aggregate. It must not rely on reconstructing authority from mutable current configuration after the fact.

Authority provenance is evidence about why the read was allowed; it is not evidence that the calendar content itself is true. Content support still flows through Observation → WorldSourceCapture → EvidenceItem.

## Acquisition and freshness

Calendar state is treated as connected-world observation, not innate knowledge.

A successful read creates an acquisition-specific `WorldSourceCapture` with at least:

```text
selected external resource identity
requested absolute date/window
captured_at
provider-resolved resource/window metadata where available
exact acquired material or normalized recoverable capture
```

A current calendar answer requires a fresh acquisition for the current user interaction unless the runtime is recovering the same already-completed interaction from a durable capture/result that still satisfies the same request contract.

A read retry after a failed/unknown transport attempt creates a new Observation. Because the operation is read-only, uncertainty concerns what was observed, not an external mutation. No `Effect` is created for the read.

## Personal-world result semantics

The admitted result must remain visibly distinct from memory and public-world search.

Conceptually, the projection must carry a source classification equivalent to:

```text
CURRENT_PERSONAL_OBSERVATION
```

User-facing language may therefore use forms such as:

```text
"From your calendar, I can see..."
"I checked your calendar..."
```

only after an authorized acquisition and evidence-backed result exist.

The model may summarize the selected calendar window, but it cannot decide which calendar to access, broaden the date range, fetch another resource, or convert observed events into memory.

## Data minimization

The first slice reads only the requested calendar and requested absolute date window. It must not ingest the full calendar history, unrelated calendars, contact directories, message bodies, file stores, or application state merely because the credential technically permits access.

Provider technical scope is a ceiling, not Alsoul authority.

## No silent memory admission

Calendar content is retained only in the evidence/result lineage required for the authorized interaction and recovery. The read path creates no `MemoryClaim` or `PersonClaim` merely because an event mentions the counterpart, a preference, a location, another person, or a repeated pattern.

```text
personal data exposure
≠ memory proposal
≠ memory admission
```

A later memory feature may deliberately propose/admit selected personal-world evidence under a separate policy and user-facing contract. F5.A does not do so.

## Projection eligibility

Personal-world evidence must not become a general-purpose pool for unrelated cognition.

For the first slice, a calendar-derived WorldResult is eligible only for the interaction that caused its authorized acquisition and for deterministic recovery of that same interaction. Reuse in a different interaction requires a new explicit selection/admission contract and, for current-state questions, normally a new acquisition.

Permission revocation does not delete historical evidence or already-presented Timeline content. It does block new personal-world acquisitions and new unrelated projections that would require current access authority.

## Recovery behavior

F5.A preserves the F4 rule: resume from the furthest trustworthy durable stage.

```text
input admitted, no successful capture
    → re-evaluate current read authority, then perform a new Observation

capture/result committed, projection not yet committed
    → recover the same interaction from durable authorized evidence if request/freshness invariants still hold

projection/generated/adopted/presented committed
    → reuse the canonical downstream stage; do not re-read the calendar merely because the process restarted
```

A restart never reconstructs authority by assuming that a credential still exists or that an old Permission remains current for a new acquisition.

## F5.A fail-closed cases

The connector must not be dispatched when any of the following holds:

- unsupported personal-calendar grammar;
- zero or multiple active calendar resources under the first-slice contract;
- capability absent or unavailable;
- capability effect class missing/untrusted;
- AI policy denies the read;
- selected resource outside declared scope;
- Permission absent, unreadable, expired, revoked, or mismatched;
- CredentialBinding absent/unusable;
- credential/provider scope insufficient;
- requested date/window violates the capability or Permission constraints.

Failure occurs before model execution when no evidence-backed calendar result can be admitted.

## F5.A acceptance bar

The first tranche is complete only when executable tests prove all of the following:

1. The same `CompanionPerson`, `CounterpartPerson`, and `RelationshipState` survive connector binding, credential rebinding, and complete runtime recomposition.
2. A bounded absolute-date calendar question dispatches exactly one authorized read against exactly one selected calendar resource.
3. No connector call occurs without current Capability, AI policy, resource scope, Permission, and usable CredentialBinding.
4. Missing/unreadable authority state fails closed.
5. Provider/tool naming cannot change the trusted READ effect classification.
6. The resulting answer is traceable through Investigation → Observation → WorldSourceCapture → EvidenceItem → WorldResult → ContextProjection.
7. The Observation retains immutable authority provenance for capability, resource, permission, credential binding, and source interaction.
8. The model receives no credential secret and no authority to widen the read.
9. Calendar event content creates no MemoryClaim/PersonClaim automatically.
10. A second unrelated interaction cannot reuse the personal-world result as generic context.
11. Process loss after durable capture/result can recover without unnecessary duplicate acquisition when the same-interaction freshness contract remains valid.
12. Process loss before successful capture re-evaluates current authority before a new read.
13. Strong observational language is impossible without admitted personal-world evidence.
14. Permission revocation blocks new reads without deleting historical Timeline/evidence state.

Passing F5.A authorizes work on F5.B. It does not close F5.

# F5.B — One bounded calendar mutation

## Objective

After F5.A is stable, add exactly one effectful capability sufficient to prove the architecture in Decisions 08.A–08.B:

```text
calendar.event.create
```

The user must specify a bounded semantic event target. The host normalizes that intent into an immutable `Action`; the connector never receives authority directly from model-generated tool syntax.

A representative bounded request is:

```text
"Add 'Dentist' to my calendar on 2026-09-10 from 15:00 to 15:30."
```

Timezone, recurrence, attendees, conferencing, reminders, edits, deletes, and free-form scheduling remain outside the first write slice unless separately specified.

## Action path

```text
trusted COUNTERPART_INPUT
↓
bounded calendar-create intent
↓
resolve selected calendar resource
↓
normalize immutable Action
↓
evaluate current authority
    capability available
    AND AI policy permits write
    AND resource scope permits target
    AND Permission permits calendar.event.create
    AND current operation-specific Approval binds exact Action
    AND usable CredentialBinding/provider scope exists
↓
ExecutionAttempt persisted before dispatch
↓
external dispatch
↓
CONFIRMED_EFFECT
    OR CONFIRMED_NO_EFFECT
    OR UNKNOWN_EFFECT
```

Read Permission does not satisfy write Permission. The fact that the user previously asked a read question does not approve a later mutation.

## Approval contract

Approval binds the immutable semantic Action, including the selected resource and all effect-relevant parameters. Material change to title, date, time, resource, or other bounded parameter creates a different Action and requires new approval when policy requires approval.

A model-supplied confirmation token, tool argument, UI implementation detail, or provider response is not human Approval.

## Effect truth

Completion language is downstream of evidence-backed Effect state.

```text
"I created the event."
```

requires `CONFIRMED_EFFECT` for the intended calendar event creation.

A transport timeout after possible dispatch produces `UNKNOWN_EFFECT`, not failure and not success.

While `UNKNOWN_EFFECT` remains unresolved, blind mutation retry is prohibited.

## Reconciliation

Unknown calendar-create effects are reconciled through the read side:

```text
UNKNOWN_EFFECT
↓
authorized calendar.events.read
↓
Investigation / Observation / Capture
↓
match capability-specific external evidence
↓
CONFIRMED_EFFECT
OR CONFIRMED_NO_EFFECT
OR still UNKNOWN_EFFECT
```

Reconciliation is observation, not a second create Action.

## F5.B acceptance bar

F5.B is complete only when tests prove:

1. read authority cannot authorize write;
2. one immutable Action captures the exact semantic calendar-create intent;
3. changed effect-relevant parameters require a new Action/Approval;
4. each concrete dispatch is a distinct ExecutionAttempt under the same Action;
5. external idempotency identity, when supported, is stable per Action rather than derived solely from payload equality;
6. Effect is admitted only from capability-sufficient evidence;
7. timeout/ambiguous dispatch persists `UNKNOWN_EFFECT` across restart;
8. `UNKNOWN_EFFECT` blocks blind retry;
9. reconciliation uses read-side observation and can resolve success, no-effect, or continued uncertainty;
10. presentation/model failure after confirmed Effect cannot cause the Action to execute again;
11. credential rotation can change execution binding without redefining the semantic Action or Person;
12. strong completion language is mechanically blocked until the corresponding Effect is confirmed.

# F5 closure bar

F5 closes only when F5.A and F5.B are both green and the executable evidence demonstrates:

- personal-world provenance and freshness survive connector use;
- personal data does not silently broaden memory scope;
- authority state fails closed and remains monotonic narrowing;
- read and write authority are independently scoped;
- one bounded mutation uses explicit semantic Approval;
- attempted operation and established external Effect remain distinct;
- ambiguous effects survive restart and are reconciled instead of blindly replayed;
- credential removal/rebinding does not redefine Person identity;
- effect classification comes from trusted capability semantics rather than provider/tool naming;
- access to an application/resource does not redefine Person or Relationship identity.

## Explicit exclusions after this contract

This checkpoint does not authorize broad personal-world indexing, email sending, file mutation, contact editing, multiple-calendar natural-language routing, autonomous background access, durable delegated work, recurring triggers, proactive contact, semantic history retrieval, rich modality, or general connector/plugin execution.

Each later expansion must inherit the same authority, provenance, memory, effect, and recovery boundaries rather than bypassing them.
