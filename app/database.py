from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Creates all tables if they don't already exist."""

    import app.models  

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: provides a session and closes it after the request."""
    with Session(engine) as session:
        yield session