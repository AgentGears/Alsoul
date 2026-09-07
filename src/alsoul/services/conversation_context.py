from __future__ import annotations

import re

_CONTEXTUAL_CONVERSATIONAL_PATTERNS = (
    re.compile(
        r"^\s*what\s+do\s+you\s+think\s+(?:about|of)\s+(?:that|it)\s*\?\s*$",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"^\s*tell\s+me\s+what\s+you\s+think\s+(?:about|of)\s+(?:that|it)\s*[.!]?\s*$",
        flags=re.IGNORECASE,
    ),
)


def requires_prior_timeline_context(content_text: str) -> bool:
    """Return whether one bounded conversational form requires prior Timeline context.

    This is deliberately a narrow deterministic grammar. It does not resolve arbitrary
    pronouns or let a model decide which history should become invocation context.
    """

    return any(
        pattern.fullmatch(content_text)
        for pattern in _CONTEXTUAL_CONVERSATIONAL_PATTERNS
    )


__all__ = ["requires_prior_timeline_context"]
