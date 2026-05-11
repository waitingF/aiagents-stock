"""Repository base classes."""

from __future__ import annotations

from pathlib import Path


class SQLiteRepository:
    """Base repository that keeps database paths stable at the project root."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
