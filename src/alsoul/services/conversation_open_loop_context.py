from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

OpenLoopDirective = Literal[
    "OPEN",
    "RESOLVE",
    "CANCEL",
    "RESUME",
    "LABEL",
    "RENAME_ALIAS",
    "REMOVE_ALIAS",
    "NONE",
]
OpenLoopSelectorKind = Literal[
    "UNQUALIFIED",
    "DECISION_OPTION_PAIR",
    "USER_ALIAS",
]

DECISION_REFERENCE_KIND = "DECISION_OPTION_PAIR"
DECISION_REFERENCE_CONTRACT_VERSION = "DECISION_OPTION_PAIR_V1"
USER_ALIAS_KIND = "USER_LABEL"
USER_ALIAS_CONTRACT_VERSION = "USER_LABEL_V1"

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

_ALIAS_ASSIGN = (
    re.compile(
        r'^\s*call\s+the\s+decision\s+between\s+'
        r'(?P<option_a>[^\n."]{1,120}?)\s+and\s+'
        r'(?P<option_b>[^\n."]{1,120}?)\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
        re.IGNORECASE,
    ),
    re.compile(
        r'^\s*label\s+the\s+decision\s+between\s+'
        r'(?P<option_a>[^\n."]{1,120}?)\s+and\s+'
        r'(?P<option_b>[^\n."]{1,120}?)\s+as\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
        re.IGNORECASE,
    ),
)

_ALIAS_RESUME = re.compile(
    r'^\s*back\s+to\s+(?:the\s+)?decision\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
    re.IGNORECASE,
)
_ALIAS_RESOLVE = re.compile(
    r'^\s*resolve\s+(?:the\s+)?decision\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
    re.IGNORECASE,
)
_ALIAS_CANCEL = re.compile(
    r'^\s*cancel\s+(?:the\s+)?decision\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
    re.IGNORECASE,
)
_ALIAS_RENAME = re.compile(
    r'^\s*rename\s+(?:the\s+)?decision\s+"(?P<label>[^"\n]{1,120})"\s+'
    r'to\s+"(?P<new_label>[^"\n]{1,120})"\s*[.!]?\s*$',
    re.IGNORECASE,
)
_ALIAS_REMOVE = re.compile(
    r'^\s*remove\s+(?:the\s+)?label\s+"(?P<label>[^"\n]{1,120})"\s*[.!]?\s*$',
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class F4OpenLoopDirective:
    operation: OpenLoopDirective
    selector_kind: OpenLoopSelectorKind | None = None
    selector_contract_version: str | None = None
    selector_key: str | None = None
    option_a: str | None = None
    option_b: str | None = None
    alias_label: str | None = None
    alias_key: str | None = None
    new_alias_label: str | None = None
    new_alias_key: str | None = None

    @property
    def explicit(self) -> bool:
        return self.selector_kind in {"DECISION_OPTION_PAIR", "USER_ALIAS"}


def normalize_decision_option(value: str) -> str:
    """Apply the frozen mechanical normalization used by F4 reference v1."""

    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.strip().split())
    return normalized.casefold()


def canonicalize_decision_option_pair(option_a: str, option_b: str) -> str:
    first = normalize_decision_option(option_a)
    second = normalize_decision_option(option_b)
    if not first or not second:
        raise ValueError("decision reference options must not be empty")
    return json.dumps(sorted((first, second)), ensure_ascii=False, separators=(",", ":"))


def _try_canonicalize_decision_option_pair(option_a: str, option_b: str) -> str | None:
    try:
        return canonicalize_decision_option_pair(option_a, option_b)
    except ValueError:
        return None


def normalize_user_alias(value: str) -> str:
    """Apply the frozen mechanical normalization used by USER_LABEL_V1."""

    normalized = unicodedata.normalize("NFC", value)
    normalized = " ".join(normalized.strip().split())
    normalized = normalized.casefold()
    if not normalized:
        raise ValueError("open-loop alias must not be empty")
    return normalized


def _try_normalize_user_alias(value: str) -> str | None:
    try:
        return normalize_user_alias(value)
    except ValueError:
        return None


def _explicit_directive(operation: OpenLoopDirective, match: re.Match[str]) -> F4OpenLoopDirective:
    option_a = match.group("option_a")
    option_b = match.group("option_b")
    selector_key = _try_canonicalize_decision_option_pair(option_a, option_b)
    if selector_key is None:
        return F4OpenLoopDirective(operation="NONE")
    return F4OpenLoopDirective(
        operation=operation,
        selector_kind="DECISION_OPTION_PAIR",
        selector_contract_version=DECISION_REFERENCE_CONTRACT_VERSION,
        selector_key=selector_key,
        option_a=option_a,
        option_b=option_b,
    )


def _alias_selector(operation: OpenLoopDirective, match: re.Match[str]) -> F4OpenLoopDirective:
    label = match.group("label")
    alias_key = _try_normalize_user_alias(label)
    if alias_key is None:
        return F4OpenLoopDirective(operation="NONE")
    return F4OpenLoopDirective(
        operation=operation,
        selector_kind="USER_ALIAS",
        selector_contract_version=USER_ALIAS_CONTRACT_VERSION,
        selector_key=alias_key,
        alias_label=label,
        alias_key=alias_key,
    )


def parse_open_loop_directive(content_text: str) -> F4OpenLoopDirective:
    """Parse only the bounded provider-independent F4 decision-loop grammar."""

    opening = _DECISION_OPEN.fullmatch(content_text)
    if opening:
        return _explicit_directive("OPEN", opening)

    for pattern in _ALIAS_ASSIGN:
        match = pattern.fullmatch(content_text)
        if match:
            directive = _explicit_directive("LABEL", match)
            if directive.operation == "NONE":
                return directive
            label = match.group("label")
            alias_key = _try_normalize_user_alias(label)
            if alias_key is None:
                return F4OpenLoopDirective(operation="NONE")
            return F4OpenLoopDirective(
                operation=directive.operation,
                selector_kind=directive.selector_kind,
                selector_contract_version=directive.selector_contract_version,
                selector_key=directive.selector_key,
                option_a=directive.option_a,
                option_b=directive.option_b,
                alias_label=label,
                alias_key=alias_key,
            )

    rename = _ALIAS_RENAME.fullmatch(content_text)
    if rename:
        directive = _alias_selector("RENAME_ALIAS", rename)
        if directive.operation == "NONE":
            return directive
        new_label = rename.group("new_label")
        new_alias_key = _try_normalize_user_alias(new_label)
        if new_alias_key is None:
            return F4OpenLoopDirective(operation="NONE")
        return F4OpenLoopDirective(
            operation=directive.operation,
            selector_kind=directive.selector_kind,
            selector_contract_version=directive.selector_contract_version,
            selector_key=directive.selector_key,
            alias_label=directive.alias_label,
            alias_key=directive.alias_key,
            new_alias_label=new_label,
            new_alias_key=new_alias_key,
        )

    remove = _ALIAS_REMOVE.fullmatch(content_text)
    if remove:
        return _alias_selector("REMOVE_ALIAS", remove)

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

    alias_resume = _ALIAS_RESUME.fullmatch(content_text)
    if alias_resume:
        return _alias_selector("RESUME", alias_resume)
    alias_resolve = _ALIAS_RESOLVE.fullmatch(content_text)
    if alias_resolve:
        return _alias_selector("RESOLVE", alias_resolve)
    alias_cancel = _ALIAS_CANCEL.fullmatch(content_text)
    if alias_cancel:
        return _alias_selector("CANCEL", alias_cancel)

    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESUME):
        return F4OpenLoopDirective(operation="RESUME", selector_kind="UNQUALIFIED")
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_RESOLVE):
        return F4OpenLoopDirective(operation="RESOLVE", selector_kind="UNQUALIFIED")
    if any(pattern.fullmatch(content_text) for pattern in _DECISION_CANCEL):
        return F4OpenLoopDirective(operation="CANCEL", selector_kind="UNQUALIFIED")
    return F4OpenLoopDirective(operation="NONE")


def classify_open_loop_directive(content_text: str) -> OpenLoopDirective:
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
    "USER_ALIAS_CONTRACT_VERSION",
    "USER_ALIAS_KIND",
    "canonicalize_decision_option_pair",
    "classify_open_loop_directive",
    "closes_conversation_open_loop",
    "normalize_decision_option",
    "normalize_user_alias",
    "opens_conversation_open_loop",
    "parse_open_loop_directive",
    "requires_conversation_open_loop_context",
]
