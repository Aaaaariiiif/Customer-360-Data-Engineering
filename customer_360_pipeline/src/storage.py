"""
Storage and Target Publishing Module.
Manages DuckDB transactions, Parquet/CSV publishing, and idempotent load operations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Union
import duckdb
import pandas as pd

from src.schemas import DUCKDB_SCHEMA_DDL


class StorageManager:
    """Manages transactional loads into DuckDB and exports to Parquet/CSV formats."""

    def __init__(
        self,
        duckdb_path: Union[str, Path] = "data/output/customer_360.duckdb",
        parquet_dir: Union[str, Path] = "data/output/parquet",
        csv_dir: Union[str, Path] = "data/output",
    ):
        self.duckdb_path = str(duckdb_path)
        self.parquet_dir = Path(parquet_dir)
        self.csv_dir = Path(csv_dir)

        # Ensure parent directories exist
        if self.duckdb_path != ":memory:":
            Path(self.duckdb_path).parent.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.csv_dir.mkdir(parents=True, exist_ok=True)

        self._init_duckdb_schema()

    def _init_duckdb_schema(self):
        """Initializes tables in DuckDB database if they do not exist."""
        conn = duckdb.connect(self.duckdb_path)
        try:
            for table_name, ddl in DUCKDB_SCHEMA_DDL.items():
                conn.execute(ddl)
        finally:
            conn.close()

    def get_connection(self) -> duckdb.DuckDBPyConnection:
        """Returns an active DuckDB connection."""
        return duckdb.connect(self.duckdb_path)

    def publish_table(
        self,
        table_name: str,
        df: pd.DataFrame,
        mode: str = "overwrite",
        run_id: Optional[str] = None,
    ):
        """
        Publishes DataFrame to DuckDB idempotently:
        - If mode == 'overwrite': atomically truncates/replaces the table content.
        - If mode == 'upsert' and run_id: replaces rows matching run_id, or merges on PK.
        """
        if df is None:
            return

        conn = duckdb.connect(self.duckdb_path)
        try:
            conn.execute("BEGIN TRANSACTION")

            # Register DataFrame as a temporary view
            conn.register("stage_df", df)

            if mode == "overwrite":
                conn.execute(f"DELETE FROM {table_name}")
                if not df.empty:
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM stage_df")
            elif run_id:
                # Idempotent delete-and-replace for specific run_id
                try:
                    conn.execute(f"DELETE FROM {table_name} WHERE run_id = '{run_id}'")
                except Exception:
                    pass
                if not df.empty:
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM stage_df")
            else:
                # Default append
                if not df.empty:
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM stage_df")

            conn.execute("COMMIT")
        except Exception as e:
            conn.execute("ROLLBACK")
            raise RuntimeError(f"Failed to publish {table_name} to DuckDB: {e}") from e
        finally:
            conn.close()

    def export_formats(
        self,
        table_name: str,
        df: pd.DataFrame,
        formats: List[str] = ("parquet", "csv"),
    ):
        """Exports DataFrame to Parquet and CSV files for analytical downstream consumers."""
        if "parquet" in formats:
            p_dir = self.parquet_dir / table_name
            p_dir.mkdir(parents=True, exist_ok=True)
            p_file = p_dir / f"{table_name}.parquet"
            df.to_parquet(p_file, index=False, engine="pyarrow")

        if "csv" in formats:
            csv_file = self.csv_dir / f"{table_name}.csv"
            df.to_csv(csv_file, index=False)

    def publish_all(
        self,
        tables: Dict[str, pd.DataFrame],
        mode: str = "overwrite",
        run_id: Optional[str] = None,
        formats: List[str] = ("duckdb", "parquet", "csv"),
    ):
        """Publishes all target, quarantine, and audit tables across selected storage layers."""
        for table_name, df in tables.items():
            if "duckdb" in formats:
                self.publish_table(table_name, df, mode=mode, run_id=run_id)

            export_fmts = [f for f in formats if f in ("parquet", "csv")]
            if export_fmts:
                self.export_formats(table_name, df, formats=export_fmts)
