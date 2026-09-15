"""Current persistence schema.

Historical schema modules remain frozen. Schema v14 extends executable F5.B through
current-authorized read-side reconciliation of unresolved calendar-create attempts.
"""

from .schema_v14 import *  # noqa: F401,F403
