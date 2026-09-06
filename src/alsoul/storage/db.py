from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import Connection

from .schema import metadata


def create_sqlite_engine(path: str | Path) -> Engine:
    engine = create_engine(f"sqlite+pysqlite:///{Path(path)}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    metadata.create_all(engine)


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    with engine.begin() as connection:
        yield connection
