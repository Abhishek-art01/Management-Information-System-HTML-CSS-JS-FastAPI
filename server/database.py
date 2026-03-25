"""
database.py — engine, session factory, and helpers.
All config is read from config.py (which reads .env).
"""
from typing import Generator

import pandas as pd
from sqlmodel import SQLModel, Session, create_engine, select, col

from config import get_settings

cfg = get_settings()

# ── Engine ────────────────────────────────────────────────────────────────────
_connect_args: dict = {}
if cfg.is_postgres:
    _connect_args = {"sslmode": "require"}
elif "sqlite" in cfg.database_url:
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    cfg.database_url,
    echo=cfg.app_debug,
    pool_pre_ping=True,
    connect_args=_connect_args,
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def create_db_and_tables() -> None:
    """Create all tables defined in SQLModel metadata."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency: one DB session per request."""
    with Session(engine) as session:
        yield session


def bulk_save_unique(session: Session, Model, df: pd.DataFrame) -> int:
    """
    Insert rows from *df* that don't yet exist in the DB (keyed on unique_id).
    Returns the number of newly inserted rows.
    """
    if df.empty or "unique_id" not in df.columns:
        return 0

    new_ids = df["unique_id"].dropna().unique().tolist()
    existing = set(
        session.exec(
            select(Model.unique_id).where(col(Model.unique_id).in_(new_ids))
        ).all()
    )

    new_rows = df[~df["unique_id"].isin(existing)]
    if new_rows.empty:
        return 0

    objects = [Model(**row) for row in new_rows.to_dict(orient="records")]
    session.add_all(objects)
    session.commit()
    return len(objects)
