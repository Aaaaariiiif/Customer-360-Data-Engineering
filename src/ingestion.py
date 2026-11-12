"""
Data Ingestion Module.
Loads raw files (CSV, JSON, Parquet) with schema validation and metadata tracking.
Handles empty files, corrupt headers, and tracks ingestion lineage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd

from src.schemas import (
    SOURCE_CUSTOMER_COLUMNS,
    SOURCE_ACCOUNT_COLUMNS,
    SOURCE_ORDER_COLUMNS,
    SOURCE_INTERACTION_COLUMNS,
)


@dataclass
class IngestedDataset:
    table_name: str
    file_path: str
    row_count: int
    column_count: int
    df: pd.DataFrame
    ingested_at: str
    status: str = "SUCCESS"
    error_message: Optional[str] = None


class IngestionEngine:
    """Handles raw data ingestion from local directories or storage buckets."""

    EXPECTED_SCHEMAS: Dict[str, List[str]] = {
        "customers": SOURCE_CUSTOMER_COLUMNS,
        "accounts": SOURCE_ACCOUNT_COLUMNS,
        "orders": SOURCE_ORDER_COLUMNS,
        "interactions": SOURCE_INTERACTION_COLUMNS,
    }

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.ingestion_timestamp = datetime.now(timezone.utc).isoformat()

    def _read_file(self, file_path: Path) -> pd.DataFrame:
        """Read CSV, JSON, or Parquet file into pandas DataFrame."""
        if not file_path.exists():
            raise FileNotFoundError(f"Input file does not exist: {file_path}")

        # Check empty 0-byte file
        if file_path.stat().st_size == 0:
            return pd.DataFrame()

        ext = file_path.suffix.lower()
        if ext == ".csv":
            try:
                # Read with strings as object / string type to avoid unexpected float coercion of IDs or phones
                df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
                return df
            except pd.errors.EmptyDataError:
                return pd.DataFrame()
        elif ext in (".json", ".jsonl"):
            try:
                df = pd.read_json(file_path, lines=True, dtype=False)
                return df
            except ValueError:
                return pd.DataFrame()
        elif ext == ".parquet":
            return pd.read_parquet(file_path)
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def ingest_table(self, table_name: str, file_path: Union[str, Path]) -> IngestedDataset:
        """Ingests a single table from disk, validates baseline schema, and injects lineage."""
        path = Path(file_path)
        expected_cols = self.EXPECTED_SCHEMAS.get(table_name, [])

        if not path.exists():
            # If file doesn't exist, produce empty DataFrame with expected columns
            df_empty = pd.DataFrame(columns=expected_cols)
            return IngestedDataset(
                table_name=table_name,
                file_path=str(path),
                row_count=0,
                column_count=len(expected_cols),
                df=df_empty,
                ingested_at=self.ingestion_timestamp,
                status="FILE_NOT_FOUND",
                error_message=f"File {path} not found; initialized empty schema.",
            )

        df = self._read_file(path)

        if df.empty:
            df = pd.DataFrame(columns=expected_cols)
            return IngestedDataset(
                table_name=table_name,
                file_path=str(path),
                row_count=0,
                column_count=len(expected_cols),
                df=df,
                ingested_at=self.ingestion_timestamp,
                status="EMPTY",
            )

        # Ensure all expected columns exist, fill missing with empty string
        for col in expected_cols:
            if col not in df.columns:
                df[col] = ""

        # Reorder columns to expected schema + extra columns
        ordered_cols = expected_cols + [c for c in df.columns if c not in expected_cols]
        df = df[ordered_cols].copy()

        # Add ingestion lineage metadata columns
        df["_source_file"] = str(path.name)
        df["_ingested_at"] = self.ingestion_timestamp
        df["_run_id"] = self.run_id

        return IngestedDataset(
            table_name=table_name,
            file_path=str(path),
            row_count=len(df),
            column_count=len(df.columns),
            df=df,
            ingested_at=self.ingestion_timestamp,
            status="SUCCESS",
        )

    def ingest_all(self, input_dir: Union[str, Path]) -> Dict[str, IngestedDataset]:
        """Ingests all 4 entities (customers, accounts, orders, interactions) from a directory."""
        dir_path = Path(input_dir)
        results: Dict[str, IngestedDataset] = {}

        entity_filenames = {
            "customers": ["customers.csv", "customers.parquet", "customers.jsonl"],
            "accounts": ["accounts.csv", "accounts.parquet", "accounts.jsonl"],
            "orders": ["orders.csv", "orders.parquet", "orders.jsonl"],
            "interactions": ["interactions.csv", "interactions.parquet", "interactions.jsonl"],
        }

        for table_name, file_candidates in entity_filenames.items():
            found_path = None
            for fname in file_candidates:
                candidate = dir_path / fname
                if candidate.exists():
                    found_path = candidate
                    break

            if found_path is None:
                # Fallback to default expected path even if missing
                found_path = dir_path / f"{table_name}.csv"

            results[table_name] = self.ingest_table(table_name, found_path)

        return results
