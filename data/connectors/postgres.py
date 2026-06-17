"""PostgreSQL / MySQL connector — L8 data platform."""
from __future__ import annotations

import os
import pandas as pd
from sqlalchemy import create_engine, text, inspect


class PostgresConnector:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or os.environ.get("POSTGRES_URL", "")
        self._engine = create_engine(self._url) if self._url else None

    def query(self, sql: str) -> pd.DataFrame:
        if not self._engine:
            raise RuntimeError("POSTGRES_URL not configured")
        with self._engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def list_tables(self, schema: str = "public") -> list[str]:
        if not self._engine:
            return []
        inspector = inspect(self._engine)
        return inspector.get_table_names(schema=schema)

    def get_schema(self, table: str, schema: str = "public") -> list[dict]:
        if not self._engine:
            return []
        inspector = inspect(self._engine)
        return inspector.get_columns(table, schema=schema)

    def execute(self, sql: str) -> None:
        if not self._engine:
            raise RuntimeError("POSTGRES_URL not configured")
        with self._engine.begin() as conn:
            conn.execute(text(sql))
