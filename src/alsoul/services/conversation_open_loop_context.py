from __future__ import annotations

import re
from typing import Literal

OpenLoopDirective = Literal["OPEN", "RESOLVE", "CANCEL", "RESUME", "NONE"]

_DECISION_OPEN = re.compile(
    r"^\s*i\s+need\s+to\s+decide\s+between\s+"
    r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
    r"(?P<option_b>[^\n.]{1,120}?)\s*[.!]?\s*$",
    flags=re.IGNORECASE,
)

_DECISION_RESUME = (
    re.compile(r"^\s*back\s+to\s+(?:that|the)\s+decision\s*[.!]?\s*$", re.IGNORECASE),
    re.compile(
        r"^\s*(?:let(?:'s|\s+us))\s+go\s+back\s+to\s+(?:that|the)\s+decision\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)

_DECISION_RESOLVE = (
    re.compile(r"^\s*i\s+made\s+that\s+decision\s*[.!]?\s*$", re.IGNORECASE),
    re.compile(r"^\s*that\s+decision\s+is\s+settled\s*[.!]?\s*$", re.IGNORECASE),
)

_DECISION_CANCEL = (
    re.compile(
        r"^\s*(?:let(?:'s|\s+us))\s+drop\s+that\s+decision\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)


def classify_open_loop_directive(content_text: str) -> OpenLoopDirective:
    """Classify only the bounded F4 decision-loop forms.

    The grammar is provider-independent and deliberately does not perform semantic
    search over history. Opening text establishes a conversational dependency;
    resume/closure forms may resolve only an unambiguous durable loop later.
    """

    if _DECISION_OPEN.fullmatch(content_text):
        return "OPEN"
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESUME):
        return "RESUME"
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESOLVE):
        return "RESOLVE"
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_CANCEL):
        return "CANCEL"
    return "NONE"


def opens_conversation_open_loop(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) == "OPEN"


def requires_conversation_open_loop_context(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) == "RESUME"


def closes_conversation_open_loop(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) in {"RESOLVE", "CANCEL"}


__all__ = [
    "OpenLoopDirective",
    "classify_open_loop_directive",
    "closes_conversation_open_loop",
    "opens_conversation_open_loop",
    "requires_conversation_open_loop_context",
]
