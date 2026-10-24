"""
SQLAlchemy engine, session factory, and FastAPI dependency for the Sprout app.

Engine is created from ``settings.database_url`` (SQLite only).  Two PRAGMAs
are registered via a ``connect`` event listener so they are applied to every
new connection:

* ``PRAGMA foreign_keys = ON``   — enforce FK constraints in SQLite
* ``PRAGMA journal_mode = WAL``  — allow concurrent readers during writes

``SessionLocal`` is a plain sync sessionmaker (no async).

``get_session()`` is the FastAPI dependency; it yields a Session and always
closes it in the ``finally`` block.

``reset_db()`` drops all tables, recreates them, and seeds with demo data.
Imports of ``Base`` and ``seed`` are deferred inside the function body to
avoid circular-import issues at module load time.

Note: ``create_all`` and ``seed`` are intentionally *not* called at module
level — startup is handled by ``app/main.py``.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    """Apply SQLite-specific PRAGMAs on every new connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(engine, expire_on_commit=False)

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_session() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Database reset (used by demo panel and Makefile ``reset`` target)
# ---------------------------------------------------------------------------


def reset_db() -> None:
    """Drop all tables, recreate the schema, and populate seed data.

    Imports are deferred to avoid circular dependencies:
    - ``Base`` lives in ``app.db.models`` which imports nothing from this module.
    - ``seed`` lives in the top-level ``seed`` module which imports from this
      module, so importing it at the top of this file would create a cycle.
    """
    from app.db.models import Base  # noqa: PLC0415
    from seed import seed  # noqa: PLC0415

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed()
