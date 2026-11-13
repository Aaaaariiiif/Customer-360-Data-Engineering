"""
Happy path automated test.
Validates end-to-end ingestion, validation, entity resolution, transformation,
publishing, and reconciliation on clean data.
"""

import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from src.config import PipelineConfig
from src.generator import DataGenerator
from src.pipeline import Customer360Pipeline


def test_end_to_end_happy_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        labels_dir = tmp_path / "expected_labels"

        # Generate clean sample data
        generator = DataGenerator(seed=123)
        counts = generator.generate(scale="small", output_dir=in_dir, labels_dir=labels_dir)
        assert counts["customers"] > 0
        assert counts["accounts"] > 0
        assert counts["orders"] > 0
        assert counts["interactions"] > 0

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)

        db_path = out_dir / "test_happy.duckdb"
        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_HAPPY_PATH_RUN",
            mode="overwrite",
            duckdb_path=str(db_path),
        )

        assert result.status == "PASSED"
        assert result.metrics.total_golden_customers > 0
        assert result.metrics.total_valid_rows > 0
        assert result.reconciliation_report.failed_checks == 0

        # Query DuckDB directly to verify tables exist and are populated
        conn = duckdb.connect(str(db_path))
        try:
            golden_count = conn.execute("SELECT COUNT(*) FROM dim_unified_customer").fetchone()[0]
            bridge_count = conn.execute("SELECT COUNT(*) FROM bridge_customer_source_map").fetchone()[0]
            summary_count = conn.execute("SELECT COUNT(*) FROM fact_customer_360_summary").fetchone()[0]

            assert golden_count > 0
            assert bridge_count >= golden_count
            assert summary_count == golden_count

            # Verify Parquet and CSV files exist
            assert (out_dir / "dim_unified_customer.csv").exists()
            assert (out_dir / "parquet" / "dim_unified_customer" / "dim_unified_customer.parquet").exists()
        finally:
            conn.close()
