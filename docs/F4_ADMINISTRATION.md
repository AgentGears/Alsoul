# F4 Administration and First-Run Bootstrap

**Status:** Implemented foundation checkpoint

The F4 runtime now has an explicit administration boundary for creating persistent storage, advancing schema revisions, and creating the initial Person/Counterpart/Relationship identity graph. Ordinary runtime execution remains unable to perform any of those operations.

## Core boundary

```text
package installation
≠ schema initialization
≠ schema migration
≠ foundation identity bootstrap
≠ ordinary runtime
≠ recovery
```

The process split is deliberate:

```text
alsoul-admin
    ├── initialize-store
    ├── migrate-store
    ├── status
    └── bootstrap-foundation

alsoul-host
    ├── ready
    ├── ingest
    ├── interact
    ├── diagnose
    ├── probe-model-contract
    └── respond
```

`alsoul-admin` is an operator-controlled mutation boundary. `alsoul-host` remains the ordinary interaction/recovery boundary and never calls administration as a repair strategy.

## Permanent distinctions

```text
storage exists ≠ schema compatible
schema compatible ≠ identity bootstrapped
identity bootstrapped ≠ runtime ready for remote providers
runtime recovery ≠ bootstrap
missing Person ≠ permission to create a new Person
missing Relationship ≠ permission to create a new Relationship
```

A missing canonical identity root is still a hard recovery failure. Administration is not an automatic fallback.

## Packaged migration environment

The migration environment now lives under:

```text
src/alsoul/migrations/
```

so the migration graph is part of the installed Alsoul package rather than depending on an untracked runtime working directory. The current packaged head is:

```text
0001_f4_foundation
```

The repository-level `alembic.ini` points at the same packaged migration environment used by `alsoul-admin`.

## Initialize a new store

```text
alsoul-admin initialize-store --database ./alsoul.db
```

Initialization has strong first-run semantics:

- the parent directory must already exist;
- the target database path must not already exist;
- the path is reserved with exclusive creation before migration begins;
- initialization never overwrites an existing file;
- the fresh database is migrated to the packaged schema head;
- if initialization fails, the newly reserved database is removed rather than being reported as successfully initialized.

The operation returns only administration metadata such as the resolved database path and schema revision.

## Migrate an existing store

```text
alsoul-admin migrate-store --database ./alsoul.db
```

Migration is explicit and separate from runtime startup. `alsoul-host` never upgrades schema as a side effect of `ready`, ingress, response execution, or recovery.

A missing database is not implicitly created by `migrate-store`; first creation remains `initialize-store`.

## Inspect administration state

```text
alsoul-admin status --database ./alsoul.db
```

The status operation is content-free. It derives:

```text
database existence/accessibility
schema revision
packaged head revision
whether schema is at head
missing table/column names, if any
foundation identity state
root object counts
```

Foundation state is one of:

```text
NOT_READY
EMPTY
BOOTSTRAPPED
INCONSISTENT
```

This is operator diagnostic state, not a canonical mutable `status` aggregate stored in the database.

## Bootstrap the F4 identity graph

After schema initialization:

```text
alsoul-admin bootstrap-foundation \
  --database ./alsoul.db \
  --identity-namespace local.first_party \
  --external-subject user-1
```

Optional explicit route arguments are available for the first-party surface and channel bindings.

The bootstrap transaction creates the F4 roots:

```text
CompanionPerson P1
↓
SelfRevision / SelfHead

CounterpartPerson U1
↓
CounterpartIdentityBinding

P1 + U1
↓
RelationshipState R1
↓
RelationshipRevision / RelationshipHead
↓
RelationshipTimelineHead

P1
├── SurfaceBinding
└── ChannelBinding
```

`bootstrap-foundation` invokes `FoundationBootstrapper` with `require_empty=True`, so all canonical foundation root tables are re-checked inside the same bootstrap transaction. If any root already exists, the first-run bootstrap fails rather than creating a second or replacement identity graph.

The lower-level `FoundationBootstrapper` remains an explicit graph-creation boundary and can be used without the empty-store fence in controlled tests or future administration workflows that deliberately create more than one graph. The first-run `alsoul-admin` command is intentionally stricter.

A partially existing graph also blocks first-run bootstrap. Administration does not silently repair or replace canonical identity.

## Runtime fail-closed rule

A schema-ready but identity-empty database is a valid administration state and an invalid interaction identity state.

The acceptance path explicitly proves:

```text
initialize-store
↓
schema is ready
↓
no CompanionPerson / CounterpartPerson / RelationshipState exists
↓
alsoul-host ready succeeds structurally
↓
trusted ingress arrives
↓
first missing route/identity binding fails closed
↓
no identity object is created
↓
foundation remains EMPTY
```

This preserves the core recovery rule:

> Ordinary runtime may recover existing identity, but it may not manufacture replacement identity when canonical roots are absent.

## First-run sequence

A minimal local first-run sequence is now:

```text
1. install Alsoul
2. alsoul-admin initialize-store --database ./alsoul.db
3. alsoul-admin status --database ./alsoul.db
4. alsoul-admin bootstrap-foundation ...
5. alsoul-admin status --database ./alsoul.db
6. create host configuration for that database
7. alsoul-host --config ./host.json ready
8. admit/interact only through trusted first-party ingress
```

The remote world, model, and presentation routes remain runtime configuration. They do not participate in schema or identity bootstrap.

## Deliberate exclusions

This checkpoint does not add:

- automatic first-user discovery;
- model-based identity creation or matching;
- migration during ordinary host startup;
- automatic repair of corrupted or partial identity graphs;
- multi-person administration inside one F4 store;
- credential provisioning;
- Permission or Approval administration;
- public network authentication;
- background tasks or proactivity.

The purpose is narrower: make a fresh F4 installation reproducibly initializable while preserving the hard boundary between administration and ordinary companion runtime.
