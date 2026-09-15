"""Current persistence schema.

Historical schema modules remain frozen. Schema v11 extends executable F5.B through
per-Action ExecutionAttempt serialization and exact durable dispatch fencing.
"""

from .schema_v11 import *  # noqa: F401,F403
