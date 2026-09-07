"""Current persistence schema.

Schema v1 remains frozen so the initial migration stays reproducible. Schema v2
extends the executable foundation with durable ConversationOpenLoop persistence.
"""

from .schema_v2 import *  # noqa: F401,F403
