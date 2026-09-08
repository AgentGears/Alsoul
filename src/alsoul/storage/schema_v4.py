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

from . import schema_v3 as _schema_v3

# Compose the current runtime metadata from a clone of frozen schema v3.
metadata = MetaData()
for _table in _schema_v3.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v3).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


conversation_open_loop_alias = Table(
    "conversation_open_loop_alias",
    metadata,
    Column("open_loop_alias_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "open_loop_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop.open_loop_id"),
        nullable=False,
    ),
    Column("alias_kind", String(64), nullable=False),
    Column("alias_contract_version", String(64), nullable=False),
    Column("display_label", String(240), nullable=False),
    Column("canonical_alias_key", String(512), nullable=False),
    Column(
        "source_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
        unique=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "alias_kind IN ('USER_LABEL')",
        name="ck_conversation_open_loop_alias_kind_f4",
    ),
    CheckConstraint(
        "alias_contract_version IN ('USER_LABEL_V1')",
        name="ck_conversation_open_loop_alias_contract_f4",
    ),
)

Index(
    "ix_conversation_open_loop_alias_lookup",
    conversation_open_loop_alias.c.alias_kind,
    conversation_open_loop_alias.c.alias_contract_version,
    conversation_open_loop_alias.c.canonical_alias_key,
)


conversation_open_loop_alias_retirement = Table(
    "conversation_open_loop_alias_retirement",
    metadata,
    Column("alias_retirement_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "open_loop_alias_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
        nullable=False,
        unique=True,
    ),
    Column("retirement_kind", String(32), nullable=False),
    Column(
        "source_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "replacement_alias_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
    ),
    Column("retired_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "retirement_kind IN ('REMOVED', 'RENAMED')",
        name="ck_conversation_open_loop_alias_retirement_kind_f4",
    ),
    CheckConstraint(
        "((retirement_kind = 'REMOVED' AND replacement_alias_id IS NULL) "
        "OR (retirement_kind = 'RENAMED' AND replacement_alias_id IS NOT NULL))",
        name="ck_conversation_open_loop_alias_retirement_shape_f4",
    ),
)


context_projection_open_loop_alias_selector = Table(
    "context_projection_open_loop_alias_selector",
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
        "open_loop_alias_id",
        Uuid(as_uuid=True),
        ForeignKey("conversation_open_loop_alias.open_loop_alias_id"),
        nullable=False,
    ),
    Column("selection_basis", String(64), nullable=False),
    Column("selector_contract_version", String(64), nullable=False),
    Column("selector_key", String(512), nullable=False),
    CheckConstraint(
        "selection_basis IN ('EXPLICIT_USER_ALIAS')",
        name="ck_projection_open_loop_alias_selector_basis_f4",
    ),
    CheckConstraint(
        "selector_contract_version IN ('USER_LABEL_V1')",
        name="ck_projection_open_loop_alias_selector_contract_f4",
    ),
    UniqueConstraint(
        "projection_id",
        "open_loop_alias_id",
        name="uq_projection_open_loop_alias_selector",
    ),
)
