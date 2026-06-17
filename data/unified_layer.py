"""L8 · Unified data layer — single interface over all connectors."""
from __future__ import annotations

import pandas as pd
from data.connectors.postgres import PostgresConnector
from data.connectors.snowflake import SnowflakeConnector
from data.connectors.bigquery import BigQueryConnector
from data.connectors.csv_excel import CSVExcelConnector
from data.connectors.duckdb_connector import DuckDBConnector


class UnifiedDataLayer:
    """Route queries to the right connector based on source type."""

    def __init__(self) -> None:
        self._postgres = PostgresConnector()
        self._snowflake = SnowflakeConnector()
        self._bigquery = BigQueryConnector()
        self._csv = CSVExcelConnector()
        self._duckdb = DuckDBConnector()  # in-process analytics engine

    @property
    def duckdb(self) -> DuckDBConnector:
        """Direct access to DuckDB for ad-hoc analytical queries."""
        return self._duckdb

    def query(self, source: str, sql_or_file: str, **kwargs) -> pd.DataFrame:
        if source == "postgres":
            return self._postgres.query(sql_or_file)
        elif source == "snowflake":
            return self._snowflake.query(sql_or_file)
        elif source == "bigquery":
            return self._bigquery.query(sql_or_file)
        elif source in ("csv", "excel"):
            return self._csv.load(sql_or_file, **kwargs)
        elif source == "duckdb":
            # sql_or_file can be a SQL string or a file path
            import os
            if os.path.exists(sql_or_file):
                return self._duckdb.query_file(sql_or_file, kwargs.get("sql"))
            return self._duckdb.query(sql_or_file)
        else:
            raise ValueError(f"Unknown source: {source}")

    def analyze_file(self, file_path: str, question: str | None = None) -> dict:
        """
        Load a file into DuckDB and return a quick profile + optional analytical result.
        Used by BI pipeline to get real data insights without a database server.
        """
        import os
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        df = self._duckdb.query_file(file_path)
        self._duckdb.register_df("uploaded_data", df)
        profile = self._duckdb.quick_profile("uploaded_data")
        result = {"profile": profile, "sample": df.head(5).to_dict(orient="records"), "source_table": "uploaded_data"}
        if question:
            result["question"] = question
        return result

    def list_sources(self) -> dict:
        duck_tables = self._duckdb.list_tables()
        snowflake_status = "configured" if self._snowflake.is_configured else "not_configured"
        bigquery_status = f"project: {self._bigquery._project}" if self._bigquery._project else "not_configured"
        return {
            "postgres": "configured" if self._postgres._url else "not_configured",
            "snowflake": snowflake_status,
            "bigquery": bigquery_status,
            "csv_excel": f"files: {self._csv.list_files()}",
            "duckdb": f"in-memory tables: {duck_tables}" if duck_tables else "ready (no tables loaded)",
        }

    def catalog(self) -> dict:
        """Return available tables/files across all sources."""
        catalog: dict = {}
        try:
            catalog["postgres"] = self._postgres.list_tables()
        except Exception as e:
            catalog["postgres_error"] = str(e)
        try:
            catalog["snowflake"] = self._snowflake.list_tables() if self._snowflake.is_configured else []
        except Exception as e:
            catalog["snowflake_error"] = str(e)
        catalog["bigquery"] = []
        catalog["bigquery_project"] = self._bigquery._project if self._bigquery._project else "not_configured"
        try:
            catalog["csv_files"] = self._csv.list_files()
        except Exception as e:
            catalog["csv_error"] = str(e)
        try:
            catalog["duckdb_tables"] = self._duckdb.list_tables()
        except Exception as e:
            catalog["duckdb_error"] = str(e)
        return catalog
