from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# SQLite + многопоточность FastAPI = нужен check_same_thread=False.
# Это безопасно, потому что SQLModel/SQLAlchemy сами управляют сессиями.
connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Создаёт все таблицы, если их ещё нет."""
    # Импорт нужен, чтобы SQLModel знал о моделях до create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI-зависимость: выдаёт сессию и закрывает её после запроса."""
    with Session(engine) as session:
        yield session