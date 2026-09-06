"""Current persistence schema.

F4 starts at schema v1. The versioned schema module is kept frozen so the initial
migration remains reproducible after later schema versions are introduced.
"""

from .schema_v1 import *  # noqa: F401,F403
