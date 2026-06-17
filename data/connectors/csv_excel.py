"""CSV / Excel connector — L8 data platform."""
from __future__ import annotations

from pathlib import Path
import pandas as pd


class CSVExcelConnector:
    def __init__(self, base_dir: str = "./data/files") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def load(self, filename: str, sheet: str | int = 0) -> pd.DataFrame:
        path = self._base / filename
        if filename.endswith((".xlsx", ".xls")):
            return pd.read_excel(path, sheet_name=sheet)
        return pd.read_csv(path)

    def list_files(self) -> list[str]:
        return [
            f.name for f in self._base.iterdir()
            if f.suffix in (".csv", ".xlsx", ".xls")
        ]

    def profile(self, filename: str) -> dict:
        df = self.load(filename)
        return {
            "filename": filename,
            "rows": len(df),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "null_counts": df.isnull().sum().to_dict(),
        }
