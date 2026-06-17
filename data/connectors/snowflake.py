"""Snowflake connector — L8 data platform."""
from __future__ import annotations

import os
import pandas as pd
from sqlalchemy import create_engine, text


def _build_url() -> str:
    account = os.environ.get("SNOWFLAKE_ACCOUNT", "")
    user = os.environ.get("SNOWFLAKE_USER", "")
    password = os.environ.get("SNOWFLAKE_PASSWORD", "")
    db = os.environ.get("SNOWFLAKE_DATABASE", "")
    warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "")
    schema = os.environ.get("SNOWFLAKE_SCHEMA", "PUBLIC")
    return (
        f"snowflake://{user}:{password}@{account}/{db}/{schema}"
        f"?warehouse={warehouse}"
    )


class SnowflakeConnector:
    def __init__(self) -> None:
        self._url = _build_url()
        self._engine = None

    @property
    def is_configured(self) -> bool:
        return bool(
            os.environ.get("SNOWFLAKE_ACCOUNT", "")
            and os.environ.get("SNOWFLAKE_USER", "")
            and os.environ.get("SNOWFLAKE_PASSWORD", "")
            and os.environ.get("SNOWFLAKE_DATABASE", "")
        )

    def _get_engine(self):
        if not self._engine:
            if not self.is_configured:
                raise RuntimeError("Snowflake connection is not configured")
            self._engine = create_engine(self._url)
        return self._engine

    def query(self, sql: str) -> pd.DataFrame:
        engine = self._get_engine()
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    def list_tables(self, schema: str = "PUBLIC", database: str | None = None) -> list[str]:
        db = database or os.environ.get("SNOWFLAKE_DATABASE", "")
        df = self.query(f"SHOW TABLES IN SCHEMA {db}.{schema}")
        return df["name"].tolist() if "name" in df.columns else []
