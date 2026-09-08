"""Current persistence schema.

Historical schema modules remain frozen. Schema v4 extends the executable foundation
with durable counterpart-authored ConversationOpenLoop aliases, append-oriented alias
retirement, and alias-selection projection provenance.
"""

from .schema_v4 import *  # noqa: F401,F403
