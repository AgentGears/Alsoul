"""Current persistence schema.

Historical schema modules remain frozen. Schema v9 begins executable F5.B with
calendar-create policy, write Permission provenance, and immutable Action admission.
"""

from .schema_v9 import *  # noqa: F401,F403
