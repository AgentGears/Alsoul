"""Current persistence schema.

Historical schema modules remain frozen. Schema v3 extends the executable foundation
with durable targetable ConversationOpenLoop references and projection selector
provenance.
"""

from .schema_v3 import *  # noqa: F401,F403
