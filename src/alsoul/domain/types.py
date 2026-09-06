from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdGenerator(Protocol):
    def new(self) -> UUID: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class UUIDGenerator:
    def new(self) -> UUID:
        return uuid4()


@dataclass(slots=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class SequenceIdGenerator:
    """Deterministic UUID generator for tests.

    IDs remain opaque to domain logic; deterministic generation only improves test readability.
    """

    def __init__(self, start: int = 1) -> None:
        self._next = start

    def new(self) -> UUID:
        value = UUID(int=self._next)
        self._next += 1
        return value
