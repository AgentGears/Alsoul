from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
)

from . import schema_v2 as _schema_v2

# Compose the current runtime metadata from a clone of frozen schema v2. Migration
# 0002 imports no current runtime metadata, but retaining this version boundary keeps
# every historical schema independently reproducible.
metadata = MetaData()
for _table in _schema_v2.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v2).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


conversation_open_loop_reference = Table(
    "conversation_open_loop_reference",
    metadata,
    Column("open_loop_reference_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "open_loop_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop.open_loop_id"),
        nullable=False,
    ),
    Column("reference_kind", String(64), nullable=False),
    Column("reference_contract_version", String(64), nullable=False),
    Column("canonical_reference_key", String(512), nullable=False),
    Column(
        "source_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "reference_kind IN ('DECISION_OPTION_PAIR')",
        name="ck_conversation_open_loop_reference_kind_f4",
    ),
    CheckConstraint(
        "reference_contract_version IN ('DECISION_OPTION_PAIR_V1')",
        name="ck_conversation_open_loop_reference_contract_f4",
    ),
    UniqueConstraint(
        "open_loop_id",
        "reference_kind",
        "reference_contract_version",
        name="uq_conversation_open_loop_reference_contract",
    ),
)

Index(
    "ix_conversation_open_loop_reference_lookup",
    conversation_open_loop_reference.c.reference_kind,
    conversation_open_loop_reference.c.reference_contract_version,
    conversation_open_loop_reference.c.canonical_reference_key,
)


context_projection_open_loop_selector = Table(
    "context_projection_open_loop_selector",
    metadata,
    Column(
        "projection_id",
        Uuid(as_uuid=True),
        ForeignKey("context_projection.projection_id"),
        primary_key=True,
    ),
    Column(
        "open_loop_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop.open_loop_id"),
        nullable=False,
    ),
    Column(
        "open_loop_reference_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop_reference.open_loop_reference_id"),
    ),
    Column("selection_basis", String(64), nullable=False),
    Column("selector_contract_version", String(64)),
    Column("selector_key", String(512)),
    CheckConstraint(
        "selection_basis IN ('CURRENT_OPEN_DECISION_LOOP', 'EXPLICIT_DECISION_REFERENCE')",
        name="ck_projection_open_loop_selector_basis_f4",
    ),
    CheckConstraint(
        "((selection_basis = 'CURRENT_OPEN_DECISION_LOOP' "
        "AND open_loop_reference_id IS NULL "
        "AND selector_contract_version IS NULL "
        "AND selector_key IS NULL) "
        "OR (selection_basis = 'EXPLICIT_DECISION_REFERENCE' "
        "AND open_loop_reference_id IS NOT NULL "
        "AND selector_contract_version IS NOT NULL "
        "AND selector_key IS NOT NULL))",
        name="ck_projection_open_loop_selector_shape_f4",
    ),
)
