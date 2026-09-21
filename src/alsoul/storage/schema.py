"""Current persistence schema.

Historical schema modules remain frozen. Schema v18 begins executable F6.A with
durable progressive-presentation session, frame, transport, and presentation evidence.
"""

from .schema_v18 import *  # noqa: F401,F403
