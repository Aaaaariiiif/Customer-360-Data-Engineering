"""
Empty input and zero-byte batch automated test.
Verifies the pipeline handles empty batches gracefully without crashing,
producing empty target schemas with zero rows.
"""

import tempfile
from pathlib import Path
import duckdb
import pytest

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline


def test_empty_input_files():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        # Create 0-byte CSV files
        for fname in ["customers.csv", "accounts.csv", "orders.csv", "interactions.csv"]:
            (in_dir / fname).touch()

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)

        db_path = out_dir / "test_empty.duckdb"
        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_EMPTY_RUN",
            mode="overwrite",
            duckdb_path=str(db_path),
        )

        assert result.metrics.total_input_rows == 0
        assert result.metrics.total_valid_rows == 0
        assert result.metrics.total_golden_customers == 0
        assert result.metrics.total_quarantined_rows == 0

        # Verify DuckDB tables exist with 0 rows
        conn = duckdb.connect(str(db_path))
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM dim_unified_customer").fetchone()[0]
            assert cnt == 0
            cnt_360 = conn.execute("SELECT COUNT(*) FROM fact_customer_360_summary").fetchone()[0]
            assert cnt_360 == 0
        finally:
            conn.close()
