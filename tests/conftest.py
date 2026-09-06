from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services.foundation import FoundationServices
from alsoul.storage import create_schema, create_sqlite_engine


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "alsoul.db"


@pytest.fixture
def services(db_path: Path, now: datetime) -> FoundationServices:
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    return FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())
