"""DuckDB connector — in-process analytical SQL engine.

Skill: duckdb-query (skills.sh/wshobson/agents)
Purpose: Run fast analytical queries on CSV/Parquet/JSON without a server.
         Used by the BI pipeline for real data analysis when files are present.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


class DuckDBConnector:
    """
    In-process analytical engine over local files and in-memory data.

    Supports:
    - CSV / Parquet / JSON / XLSX files via read_csv / read_parquet
    - Direct SQL analytics (aggregations, window functions, JOINs)
    - Auto-schema inference
    - Register pandas DataFrames as virtual tables
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = duckdb.connect(db_path)
        self._registered: set[str] = set()
        # enable httpfs for S3/GCS access if needed later
        try:
            self._conn.execute("INSTALL httpfs; LOAD httpfs;")
        except Exception:
            pass

    # ─── Query interface ────────────────────────────────────────────────────

    def query(self, sql: str) -> pd.DataFrame:
        """Execute any DuckDB SQL and return a DataFrame."""
        return self._conn.execute(sql).df()

    def query_file(self, file_path: str, sql: str | None = None) -> pd.DataFrame:
        """
        Load a CSV/Parquet/JSON/XLSX file and optionally run SQL over it.

        If no SQL is given, returns the whole file as a DataFrame.
        Use `{table}` in SQL to reference the auto-created view.
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        view_name = path.stem.replace("-", "_").replace(" ", "_")

        if ext in (".csv", ".tsv"):
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS "
                f"SELECT * FROM read_csv_auto('{path}', header=true, sample_size=1000)"
            )
        elif ext == ".parquet":
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_parquet('{path}')"
            )
        elif ext == ".json":
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {view_name} AS SELECT * FROM read_json_auto('{path}')"
            )
        elif ext in (".xlsx", ".xls"):
            # DuckDB can't read xlsx directly — load via pandas then register
            df = pd.read_excel(path)
            self.register_df(view_name, df)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        self._registered.add(view_name)
        run_sql = (sql or f"SELECT * FROM {view_name} LIMIT 100").replace("{table}", view_name)
        return self._conn.execute(run_sql).df()

    def register_df(self, name: str, df: pd.DataFrame) -> None:
        """Register a pandas DataFrame as a virtual table."""
        self._conn.register(name, df)
        self._registered.add(name)

    def schema(self, table_name: str) -> list[dict]:
        """Return column names and types for a registered table/view."""
        result = self._conn.execute(f"DESCRIBE {table_name}").fetchall()
        return [{"column": r[0], "type": r[1]} for r in result]

    def list_tables(self) -> list[str]:
        """List all tables and views in the in-memory database."""
        result = self._conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
        return [r[0] for r in result]

    # ─── BI helpers ────────────────────────────────────────────────────────

    def quick_profile(self, table_name: str) -> dict[str, Any]:
        """Row count, column count, nulls, and sample statistics."""
        try:
            row_count = self._conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            cols = self.schema(table_name)
            return {
                "table": table_name,
                "row_count": row_count,
                "column_count": len(cols),
                "columns": cols[:10],
            }
        except Exception as e:
            return {"table": table_name, "error": str(e)}

    def run_kpi_sql(self, kpi_name: str, formula_sql: str) -> dict[str, Any]:
        """
        Execute a KPI formula SQL and return the scalar result.
        formula_sql should be a SELECT that returns a single value.
        """
        try:
            result = self._conn.execute(formula_sql).fetchone()
            return {"kpi": kpi_name, "value": result[0] if result else None, "sql": formula_sql}
        except Exception as e:
            return {"kpi": kpi_name, "error": str(e), "sql": formula_sql}

    def close(self) -> None:
        self._conn.close()
