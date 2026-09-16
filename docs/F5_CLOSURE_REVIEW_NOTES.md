# F5 Closure Review Notes

**Status:** review in progress

This note records the exact review focus for the F5 closure candidate. It is not a substitute for `docs/F5_EXECUTABLE_CHECKPOINT.md` and does not weaken any acceptance item.

The closure review is specifically checking that the newly concrete mutation wire boundary preserves the already-executable semantic invariants:

- the provider wire request is an exact allowlist derived from the immutable Action, selected external resource, and stable Action correlation;
- host-only Action/ExecutionAttempt identifiers and authority provenance do not become provider payload;
- credential material is resolved only inside the trusted adapter immediately before the exact transport call;
- the transport exposes no generic arbitrary-header, tracing, retry, or raw-request persistence surface;
- redirects are not followed with mutation credentials;
- transport ambiguity is preserved as unknown and never triggers an adapter-local mutation retry;
- provider response material must fit the strict minimized response contract before crossing back to semantic services;
- durable recovery continues to use canonical Action/fence/correlation records and minimized evidence rather than a raw outbound request copy;
- credential rotation cannot silently alter an already prepared attempt;
- Person/Relationship identity remains unchanged by credential replacement.

Final closure remains conditional on exact-head Foundation CI and a clean exact-head review.
