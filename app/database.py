from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "skripsi_checker.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def _migrate_review_comments() -> None:
    inspector = inspect(engine)
    if "review_comments" not in inspector.get_table_names():
        return

    existing = {
        column["name"]
        for column in inspector.get_columns("review_comments")
    }
    additions = {
        "paragraph_index": "INTEGER",
        "selected_text": "TEXT",
        "category": "VARCHAR(50)",
        "severity": "VARCHAR(30) DEFAULT 'Moderate'",
    }

    with engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name in existing:
                continue
            connection.execute(
                text(
                    f"ALTER TABLE review_comments "
                    f"ADD COLUMN {column_name} {definition}"
                )
            )


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_review_comments()
