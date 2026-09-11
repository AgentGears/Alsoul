"""Add the first F5.A personal-calendar authority foundation.

Revision ID: 0005_personal_calendar_authority
Revises: 0004_open_loop_user_alias
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from alsoul.storage.schema_v4 import metadata as v4_metadata
from alsoul.storage.schema_v5 import metadata as v5_metadata

revision = "0005_personal_calendar_authority"
down_revision = "0004_open_loop_user_alias"
branch_labels = None
depends_on = None

_NEW_TABLE_NAMES = frozenset(v5_metadata.tables).difference(v4_metadata.tables)
_F5_RECEIPT_SCOPES = (
    "RegisterPersonalCalendarResource",
    "BindCalendarCredential",
    "GrantCalendarReadPermission",
    "ConsumeCalendarReadPermissionGrantEvent",
    "SetPersonalCalendarReadPolicy",
    "SetPersonalWorldRelationshipStatus",
    "SetPersonalResourceBindingStatus",
    "SetCredentialBindingStatus",
    "SetPermissionStatus",
    "PreparePersonalCalendarObservation",
    "FencePersonalCalendarReadPage",
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in v5_metadata.sorted_tables:
        if table.name in _NEW_TABLE_NAMES:
            table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    # F5 operation receipts can carry references to rows that disappear with this
    # downgrade, and grant-source consumption receipts would otherwise survive as
    # false single-use authority fences after a later re-upgrade. Remove exactly the
    # v5-only replay state before dropping the canonical v5 tables.
    operation_receipt = sa.table(
        "operation_receipt",
        sa.column("operation_scope", sa.String(128)),
    )
    op.execute(
        operation_receipt.delete().where(
            operation_receipt.c.operation_scope.in_(_F5_RECEIPT_SCOPES)
        )
    )

    bind = op.get_bind()
    for table in reversed(v5_metadata.sorted_tables):
        if table.name in _NEW_TABLE_NAMES:
            table.drop(bind=bind, checkfirst=False)
