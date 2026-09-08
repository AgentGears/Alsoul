from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

OpenLoopDirective = Literal["OPEN", "RESOLVE", "CANCEL", "RESUME", "NONE"]
OpenLoopSelectorKind = Literal["UNQUALIFIED", "DECISION_OPTION_PAIR"]

DECISION_REFERENCE_KIND = "DECISION_OPTION_PAIR"
DECISION_REFERENCE_CONTRACT_VERSION = "DECISION_OPTION_PAIR_V1"

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

_QUALIFIED_RESUME = (
    re.compile(
        r"^\s*back\s+to\s+the\s+decision\s+between\s+"
        r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
        r"(?P<option_b>[^\n.]{1,120}?)\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*back\s+to\s+the\s+"
        r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
        r"(?P<option_b>[^\n.]{1,120}?)\s+decision\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)

_QUALIFIED_RESOLVE = (
    re.compile(
        r"^\s*the\s+decision\s+between\s+"
        r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
        r"(?P<option_b>[^\n.]{1,120}?)\s+is\s+settled\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*i\s+made\s+the\s+decision\s+between\s+"
        r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
        r"(?P<option_b>[^\n.]{1,120}?)\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)

_QUALIFIED_CANCEL = (
    re.compile(
        r"^\s*(?:let(?:'s|\s+us)\s+)?drop\s+the\s+decision\s+between\s+"
        r"(?P<option_a>[^\n.]{1,120}?)\s+and\s+"
        r"(?P<option_b>[^\n.]{1,120}?)\s*[.!]?\s*$",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class F4OpenLoopDirective:
    operation: OpenLoopDirective
    selector_kind: OpenLoopSelectorKind | None = None
    selector_contract_version: str | None = None
    selector_key: str | None = None
    option_a: str | None = None
    option_b: str | None = None

    @property
    def explicit(self) -> bool:
        return self.selector_kind == "DECISION_OPTION_PAIR"


def normalize_decision_option(value: str) -> str:
    """Apply the frozen mechanical normalization used by F4 reference v1.

    This deliberately does not perform stemming, synonym expansion, embedding lookup,
    ontology mapping, or any other semantic interpretation.
    """

    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.strip().split())
    return normalized.casefold()


def canonicalize_decision_option_pair(option_a: str, option_b: str) -> str:
    first = normalize_decision_option(option_a)
    second = normalize_decision_option(option_b)
    if not first or not second:
        raise ValueError("decision reference options must not be empty")
    return json.dumps(sorted((first, second)), ensure_ascii=False, separators=(",", ":"))


def _explicit_directive(operation: OpenLoopDirective, match: re.Match[str]) -> F4OpenLoopDirective:
    option_a = match.group("option_a")
    option_b = match.group("option_b")
    return F4OpenLoopDirective(
        operation=operation,
        selector_kind="DECISION_OPTION_PAIR",
        selector_contract_version=DECISION_REFERENCE_CONTRACT_VERSION,
        selector_key=canonicalize_decision_option_pair(option_a, option_b),
        option_a=option_a,
        option_b=option_b,
    )


def parse_open_loop_directive(content_text: str) -> F4OpenLoopDirective:
    """Parse only the bounded provider-independent F4 decision-loop grammar."""

    opening = _DECISION_OPEN.fullmatch(content_text)
    if opening:
        return _explicit_directive("OPEN", opening)

    for pattern in _QUALIFIED_RESUME:
        match = pattern.fullmatch(content_text)
        if match:
            return _explicit_directive("RESUME", match)
    for pattern in _QUALIFIED_RESOLVE:
        match = pattern.fullmatch(content_text)
        if match:
            return _explicit_directive("RESOLVE", match)
    for pattern in _QUALIFIED_CANCEL:
        match = pattern.fullmatch(content_text)
        if match:
            return _explicit_directive("CANCEL", match)

    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESUME):
        return F4OpenLoopDirective(operation="RESUME", selector_kind="UNQUALIFIED")
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESOLVE):
        return F4OpenLoopDirective(operation="RESOLVE", selector_kind="UNQUALIFIED")
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_CANCEL):
        return F4OpenLoopDirective(operation="CANCEL", selector_kind="UNQUALIFIED")
    return F4OpenLoopDirective(operation="NONE")


def classify_open_loop_directive(content_text: str) -> OpenLoopDirective:
    """Classify only the bounded F4 decision-loop forms."""

    return parse_open_loop_directive(content_text).operation


def opens_conversation_open_loop(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) == "OPEN"


def requires_conversation_open_loop_context(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) == "RESUME"


def closes_conversation_open_loop(content_text: str) -> bool:
    return classify_open_loop_directive(content_text) in {"RESOLVE", "CANCEL"}


__all__ = [
    "DECISION_REFERENCE_CONTRACT_VERSION",
    "DECISION_REFERENCE_KIND",
    "F4OpenLoopDirective",
    "OpenLoopDirective",
    "OpenLoopSelectorKind",
    "canonicalize_decision_option_pair",
    "classify_open_loop_directive",
    "closes_conversation_open_loop",
    "normalize_decision_option",
    "opens_conversation_open_loop",
    "parse_open_loop_directive",
    "requires_conversation_open_loop_context",
]
