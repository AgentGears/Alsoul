from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)

from . import schema_v5 as _schema_v5

# Compose the current runtime metadata from a clone of frozen schema v5.
metadata = MetaData()
for _table in _schema_v5.metadata.sorted_tables:
    _table.to_metadata(metadata)

for _name, _value in vars(_schema_v5).items():
    if isinstance(_value, Table):
        globals()[_name] = metadata.tables[_value.name]


personal_calendar_acquisition_attempt = Table(
    "personal_calendar_acquisition_attempt",
    metadata,
    Column("acquisition_attempt_id", Uuid(as_uuid=True), primary_key=True),
    Column(
        "observation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_observation_scope.observation_id"),
        nullable=False,
    ),
    Column("generation", Integer, nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("adapter_binding_ref", String(256), nullable=False),
    Column("adapter_version", String(128), nullable=False),
    Column("pagination_contract_version", String(128), nullable=False),
    Column("snapshot_contract_version", String(128), nullable=False),
    Column("normalization_schema_version", String(128), nullable=False),
    Column("field_minimization_contract_version", String(128), nullable=False),
    Column("freshness_policy_version", String(128), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True)),
    Column("status", String(32), nullable=False),
    Column("failure_code", String(128)),
    UniqueConstraint(
        "observation_id",
        "generation",
        name="uq_personal_calendar_acquisition_generation",
    ),
    CheckConstraint(
        "generation >= 1",
        name="ck_personal_calendar_acquisition_generation_f5",
    ),
    CheckConstraint(
        "status IN ('STARTED', 'SUCCEEDED', 'FAILED')",
        name="ck_personal_calendar_acquisition_status_f5",
    ),
)

Index(
    "ix_personal_calendar_acquisition_observation",
    personal_calendar_acquisition_attempt.c.observation_id,
    personal_calendar_acquisition_attempt.c.generation,
)


personal_calendar_acquisition_page = Table(
    "personal_calendar_acquisition_page",
    metadata,
    Column(
        "acquisition_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_acquisition_attempt.acquisition_attempt_id"),
        primary_key=True,
    ),
    Column("page_ordinal", Integer, primary_key=True),
    Column(
        "authority_fence_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_read_authority_fence.authority_fence_id"),
        nullable=False,
        unique=True,
    ),
    Column("transport_ordinal", Integer, nullable=False),
    Column("request_cursor_digest", String(64)),
    Column("next_cursor_digest", String(64)),
    Column("snapshot_ref", Text, nullable=False),
    Column("snapshot_as_of", DateTime(timezone=True)),
    Column("event_count", Integer, nullable=False),
    Column("terminal", Boolean, nullable=False),
    Column("result_cap_hit", Boolean, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "page_ordinal >= 0",
        name="ck_personal_calendar_acquisition_page_ordinal_f5",
    ),
    CheckConstraint(
        "transport_ordinal >= 0",
        name="ck_personal_calendar_acquisition_transport_ordinal_f5",
    ),
    CheckConstraint(
        "event_count >= 0",
        name="ck_personal_calendar_acquisition_event_count_f5",
    ),
    UniqueConstraint(
        "acquisition_attempt_id",
        "transport_ordinal",
        name="uq_personal_calendar_acquisition_transport_ordinal",
    ),
)


personal_calendar_source_capture = Table(
    "personal_calendar_source_capture",
    metadata,
    Column(
        "source_capture_id",
        Uuid(as_uuid=True),
        ForeignKey("world_source_capture.source_capture_id"),
        primary_key=True,
    ),
    Column(
        "observation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_observation_scope.observation_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "acquisition_attempt_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_acquisition_attempt.acquisition_attempt_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column("snapshot_ref", Text, nullable=False),
    Column("snapshot_as_of", DateTime(timezone=True)),
    Column("freshness_anchor_at", DateTime(timezone=True), nullable=False),
    Column("freshness_anchor_basis", String(64), nullable=False),
    Column("freshness_policy_version_at_admission", String(128), nullable=False),
    Column("capability_contract_version", String(128), nullable=False),
    Column("adapter_binding_ref", String(256), nullable=False),
    Column("adapter_version", String(128), nullable=False),
    Column("pagination_contract_version", String(128), nullable=False),
    Column("snapshot_contract_version", String(128), nullable=False),
    Column("normalization_schema_version", String(128), nullable=False),
    Column("field_minimization_contract_version", String(128), nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("event_count", Integer, nullable=False),
    Column("capture_committed_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "freshness_anchor_basis IN ('PROVIDER_SNAPSHOT_AS_OF', 'ACQUISITION_STARTED_AT')",
        name="ck_personal_calendar_capture_freshness_basis_f5",
    ),
    CheckConstraint(
        "page_count >= 1",
        name="ck_personal_calendar_capture_page_count_f5",
    ),
    CheckConstraint(
        "event_count >= 0",
        name="ck_personal_calendar_capture_event_count_f5",
    ),
)


personal_calendar_world_result = Table(
    "personal_calendar_world_result",
    metadata,
    Column(
        "world_result_id",
        Uuid(as_uuid=True),
        ForeignKey("world_result.world_result_id"),
        primary_key=True,
    ),
    Column(
        "source_capture_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_source_capture.source_capture_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "observation_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_calendar_observation_scope.observation_id"),
        nullable=False,
        unique=True,
    ),
    Column(
        "personal_resource_binding_id",
        Uuid(as_uuid=True),
        ForeignKey("personal_resource_binding.personal_resource_binding_id"),
        nullable=False,
    ),
    Column(
        "source_interaction_event_id",
        Uuid(as_uuid=True),
        ForeignKey("interaction_event.event_id"),
        nullable=False,
    ),
    Column("requested_local_date", String(10), nullable=False),
    Column("freshness_anchor_at", DateTime(timezone=True), nullable=False),
    Column("freshness_policy_version_at_admission", String(128), nullable=False),
    Column("result_schema_version", String(128), nullable=False),
)
