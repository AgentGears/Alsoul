"""Add durable F4 ConversationOpenLoop persistence.

Revision ID: 0002_conversation_open_loop
Revises: 0001_f4_foundation
"""
from __future__ import annotations

from alembic import op

from alsoul.storage.schema_v2 import (
    conversation_open_loop,
    conversation_open_loop_closure,
)

revision = "0002_conversation_open_loop"
down_revision = "0001_f4_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    conversation_open_loop.create(bind=bind, checkfirst=False)
    conversation_open_loop_closure.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    conversation_open_loop_closure.drop(bind=bind, checkfirst=False)
    conversation_open_loop.drop(bind=bind, checkfirst=False)
