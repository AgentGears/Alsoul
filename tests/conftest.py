from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import Engine

from alsoul.domain.types import FixedClock, UUIDGenerator
from alsoul.services import FoundationBootstrapper, FoundationServices
from alsoul.storage import create_schema, create_sqlite_engine


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "alsoul.db"


@pytest.fixture
def engine(db_path: Path) -> Engine:
    engine = create_sqlite_engine(db_path)
    create_schema(engine)
    return engine


@pytest.fixture
def services(engine: Engine, now: datetime) -> FoundationServices:
    return FoundationServices(engine, clock=FixedClock(now), ids=UUIDGenerator())


@pytest.fixture
def bootstrapper(engine: Engine, now: datetime) -> FoundationBootstrapper:
    return FoundationBootstrapper(engine, clock=FixedClock(now), ids=UUIDGenerator())
