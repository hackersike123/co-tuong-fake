"""Database engine and session setup."""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .settings import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def get_session() -> Iterator[Session]:
    """Yield a database session and close it after the request."""
    with SessionLocal() as session:
        yield session


def upgrade_sqlite_schema(target_engine=engine) -> None:
    """Add auth columns/tables to an existing demo database without losing accounts."""
    if target_engine.dialect.name != "sqlite":
        return

    with target_engine.begin() as connection:
        inspector = inspect(connection)
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "username" not in columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(32)"))
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)")
        )

        if inspector.has_table("matches"):
            match_columns = {
                column["name"] for column in inspector.get_columns("matches")
            }
            migrations = {
                "is_public": "BOOLEAN NOT NULL DEFAULT 0",
                "has_password": "BOOLEAN NOT NULL DEFAULT 0",
                "allow_spectators": "BOOLEAN NOT NULL DEFAULT 0",
                "access_token_hashes": "TEXT NOT NULL DEFAULT '{}'",
            }
            for column_name, column_type in migrations.items():
                if column_name not in match_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE matches ADD COLUMN {column_name} {column_type}"
                        )
                    )
