from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def _column_exists(table: str, column: str) -> bool:
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        for row in result:
            # row = (cid, name, type, notnull, dflt_value, pk)
            if row[1] == column:
                return True
    return False


def _run_migrations() -> None:
    """Lightweight, idempotent migrations for SQLite."""
    # documents.user_id (added when auth was introduced)
    if _column_exists("documents", "user_id") is False:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE documents ADD COLUMN user_id INTEGER"))
        print("[migration] added documents.user_id")


def init_db() -> None:
    import app.models  # noqa: F401  ensures models are registered

    SQLModel.metadata.create_all(engine)
    _run_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session