from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def fail(code: str, message: str) -> None:
    raise DomainError(code, message)
