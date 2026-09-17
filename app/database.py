from collections.abc import Iterator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

connect_args = {"check_same_thread": False}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


# ---------- migration helpers ----------

def _table_info(table: str) -> list:
    with engine.connect() as conn:
        return conn.execute(text(f"PRAGMA table_info({table})")).fetchall()


def _add_column_if_missing(table: str, column: str, sqltype: str = "VARCHAR") -> None:
    info = _table_info(table)
    if not info:
        return  # table doesn't exist yet; create_all handles it
    names = {row[1] for row in info}
    if column in names:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sqltype}"))
    print(f"[migration] added {table}.{column}")


def _recreate_users_table_if_password_not_nullable() -> None:
    """Ensure users.password_hash allows NULL for OAuth-only accounts.

    SQLite cannot ALTER COLUMN, so the only safe way is to recreate
    the table, copy rows, then rename. Idempotent: returns early if
    password_hash is already nullable.
    """
    info = _table_info("users")
    if not info:
        return

    pw = next((row for row in info if row[1] == "password_hash"), None)
    if pw is None:
        return
    # row = (cid, name, type, notnull, dflt_value, pk)
    if pw[3] == 0:
        return  # already nullable

    print("[migration] recreating users (password_hash -> nullable)")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE users_new (
                id INTEGER NOT NULL PRIMARY KEY,
                email VARCHAR NOT NULL,
                password_hash VARCHAR,
                created_at DATETIME NOT NULL,
                plan VARCHAR NOT NULL,
                invoices_used INTEGER NOT NULL,
                invoices_limit INTEGER NOT NULL,
                usage_period_start DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO users_new
                (id, email, password_hash, created_at, plan,
                 invoices_used, invoices_limit, usage_period_start)
            SELECT id, email, password_hash, created_at, plan,
                   invoices_used, invoices_limit, usage_period_start
            FROM users
        """))
        conn.execute(text("DROP TABLE users"))
        conn.execute(text("ALTER TABLE users_new RENAME TO users"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))


def _run_migrations() -> None:
    # Documents: user_id was added when authentication was introduced.
    _add_column_if_missing("documents", "user_id", "INTEGER")

    # Users: password_hash must be nullable for OAuth accounts.
    # Do this BEFORE adding new columns so the recreate doesn't wipe them.
    _recreate_users_table_if_password_not_nullable()

    # Users: OAuth identifiers.
    _add_column_if_missing("users", "google_id", "VARCHAR")
    _add_column_if_missing("users", "github_id", "VARCHAR")


def init_db() -> None:
    import app.models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session