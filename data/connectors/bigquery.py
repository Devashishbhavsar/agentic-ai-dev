"""BigQuery connector — L8 data platform."""
from __future__ import annotations

import os
import pandas as pd


class BigQueryConnector:
    def __init__(self, project: str | None = None) -> None:
        self._project = project or os.environ.get("BIGQUERY_PROJECT", "")

    def query(self, sql: str) -> pd.DataFrame:
        from google.cloud import bigquery
        client = bigquery.Client(project=self._project)
        return client.query(sql).to_dataframe()

    def list_tables(self, dataset: str) -> list[str]:
        from google.cloud import bigquery
        client = bigquery.Client(project=self._project)
        tables = client.list_tables(dataset)
        return [t.table_id for t in tables]

    def get_schema(self, dataset: str, table: str) -> list[dict]:
        from google.cloud import bigquery
        client = bigquery.Client(project=self._project)
        ref = client.get_table(f"{self._project}.{dataset}.{table}")
        return [{"name": f.name, "type": str(f.field_type)} for f in ref.schema]
