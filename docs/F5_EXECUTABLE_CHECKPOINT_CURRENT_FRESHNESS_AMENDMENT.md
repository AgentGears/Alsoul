# F5 Executable Checkpoint — Current-Freshness Recovery Amendment

**Status:** Normative amendment to the F5 executable checkpoint  
**Publication:** GitHub-safe  
**Applies to:** [F5 Executable Checkpoint — Personal World + Trust](F5_EXECUTABLE_CHECKPOINT.md) and [Normative Addendum](F5_EXECUTABLE_CHECKPOINT_NORMATIVE_ADDENDUM.md)

This amendment is part of the F5 executable checkpoint contract. It closes the remaining recovery ambiguity for current-state personal-calendar evidence. Where this amendment is more specific about recovery freshness, it governs.

The governing distinction is:

```text
historically admitted personal-calendar evidence
≠ evidence currently eligible for new cognition
```

# Current-policy freshness is a pre-cognition gate

For F5.A, any recovery path that would create **new cognition** from a previously durable personal-calendar acquisition must evaluate that acquisition under the trusted **current** freshness policy before the next new semantic stage is admitted.

This applies whether recovery resumes from:

```text
WorldSourceCapture
WorldResult
ContextProjection
```

A previously committed `WorldResult` or `ContextProjection` does not bypass the current-policy check merely because it was fresh under the policy that governed its original admission.

Historical freshness metadata such as:

```text
captured_at
freshness_policy_version_at_admission
fresh_until_at_admission
```

remains immutable provenance. It explains the historical admission decision but is not authority to build a new projection or start a new ModelInvocation under a later policy.

# Recovery gate before new projection

When recovery has a durable personal-calendar `WorldSourceCapture` or `WorldResult` but no durable `ContextProjection`, the runtime must evaluate current freshness **before** admitting/reusing a result for projection construction.

Eligibility requires at least:

```text
same originating interaction
AND same selected PersonalResourceBinding
AND same exact requested interval
AND current trusted freshness policy is readable
AND current policy considers the capture/result eligible now
AND all other result/projection eligibility invariants still hold
```

If the current policy rejects the recovered capture/result, or current freshness cannot be evaluated, the runtime must not build a new `ContextProjection` from it. Instead it:

```text
retains the old capture/result as immutable historical provenance
↓
re-evaluates current read authority
↓
creates a new Observation / authorized acquisition
↓
admits a new WorldResult
↓
builds a new ContextProjection
```

The old capture/result is not rewritten, re-dated, or reclassified as fresh.

If recovery resumes from a durable capture from which a `WorldResult` has not yet been committed, the same current-policy test applies before a result derived from that capture can become eligible for new projection/cognition. A stale recovered capture cannot be promoted into a newly admitted current-state result merely because its original acquisition was authorized.

# Revalidation before new model invocation

The Normative Addendum already requires current-policy revalidation when a personal-calendar `ContextProjection` exists but no durable `GeneratedOutput` exists. This amendment preserves that rule and makes the stage boundary explicit:

```text
recovered capture/result
    → current-policy freshness gate before new projection

recovered projection, no GeneratedOutput
    → current-policy freshness gate before new ModelInvocation
```

If meaningful time or policy state changes between projection creation and model invocation, the second gate may invalidate a projection that was eligible when built. In that case the immutable projection remains historical provenance and a new authorized acquisition/result/projection path is required.

# Deterministic downstream recovery remains unchanged

Once a `GeneratedOutput`, adopted `CompanionOutput`, or presented output is durably committed, deterministic downstream recovery may continue from that committed stage. The runtime does not fabricate a new calendar check, and it does not mutate historical evidence to satisfy a newer freshness policy.

The freshness gate exists to prevent **new current-state cognition** from stale personal-world evidence; it does not retroactively erase already committed cognition or Timeline history.

# F5.A acceptance additions

F5.A is not complete until executable recovery tests additionally prove:

1. Process loss after `WorldResult` commit but before `ContextProjection` creation evaluates that result under the current trusted freshness policy before building a projection.
2. Tightening the freshness policy after `WorldResult` admission but before projection creation invalidates reuse even when `fresh_until_at_admission` is still in the future.
3. A recovered `WorldSourceCapture` with no committed result cannot be promoted into a new current-state `WorldResult`/projection when the current policy considers the capture stale.
4. Missing or unreadable current freshness policy blocks recovered capture/result reuse for new projection/cognition and triggers a new authorized acquisition when one can be performed.
5. A capture/result still eligible under current policy may continue through the same interaction without unnecessary duplicate acquisition.
6. Process loss after projection commit but before model generation independently rechecks current freshness before a new ModelInvocation.
7. A policy change between projection creation and model invocation can invalidate that projection and force new authorized acquisition/result/projection state.
8. Stale historical captures, results, and projections remain immutable and are never rewritten to appear fresh.
9. Already durable GeneratedOutput/adopted/presented stages remain deterministic downstream recovery and do not claim a new read occurred.

# Closure consequence

The F5 closure bar therefore requires current-policy freshness revalidation across **every pre-output recovery boundary** that can produce new cognition:

```text
capture → result/projection
result → projection
projection → model invocation
```

No historical personal-calendar admission decision is a permanent freshness token.
