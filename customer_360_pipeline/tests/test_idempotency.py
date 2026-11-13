"""
Idempotency and Rerun Safety automated tests.
Verifies that:
1. Re-running the pipeline on identical input yields identical row counts.
2. No duplicate target rows are created.
3. Deterministic Golden Customer IDs remain identical across runs.
"""

import tempfile
from pathlib import Path
import duckdb
import pytest

from src.config import PipelineConfig
from src.generator import DataGenerator
from src.pipeline import Customer360Pipeline


def test_pipeline_rerun_idempotency():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        labels_dir = tmp_path / "expected_labels"

        generator = DataGenerator(seed=42)
        generator.generate(scale="small", output_dir=in_dir, labels_dir=labels_dir)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_idempotency.duckdb"

        # -------------------------------------------------------------------
        # RUN 1
        # -------------------------------------------------------------------
        res1 = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="RUN_INITIAL_001",
            mode="overwrite",
            duckdb_path=str(db_path),
        )

        conn = duckdb.connect(str(db_path))
        try:
            dim_cust_1 = conn.execute("SELECT unified_customer_id, golden_first_name, golden_last_name FROM dim_unified_customer ORDER BY unified_customer_id").fetchall()
            bridge_cnt_1 = conn.execute("SELECT COUNT(*) FROM bridge_customer_source_map").fetchone()[0]
            summary_cnt_1 = conn.execute("SELECT COUNT(*) FROM fact_customer_360_summary").fetchone()[0]
            order_cnt_1 = conn.execute("SELECT COUNT(*) FROM fct_order_unified").fetchone()[0]
        finally:
            conn.close()

        # -------------------------------------------------------------------
        # RUN 2 (Exact rerun with mode='overwrite' or rerun scenario)
        # -------------------------------------------------------------------
        res2 = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="RUN_RERUN_002",
            mode="overwrite",
            duckdb_path=str(db_path),
        )

        conn2 = duckdb.connect(str(db_path))
        try:
            dim_cust_2 = conn2.execute("SELECT unified_customer_id, golden_first_name, golden_last_name FROM dim_unified_customer ORDER BY unified_customer_id").fetchall()
            bridge_cnt_2 = conn2.execute("SELECT COUNT(*) FROM bridge_customer_source_map").fetchone()[0]
            summary_cnt_2 = conn2.execute("SELECT COUNT(*) FROM fact_customer_360_summary").fetchone()[0]
            order_cnt_2 = conn2.execute("SELECT COUNT(*) FROM fct_order_unified").fetchone()[0]

            # 1. Row counts must be identical (no row explosion or unintended duplication)
            assert len(dim_cust_1) == len(dim_cust_2)
            assert bridge_cnt_1 == bridge_cnt_2
            assert summary_cnt_1 == summary_cnt_2
            assert order_cnt_1 == order_cnt_2

            # 2. Golden Customer IDs must be identical (deterministic hashing stability)
            for c1, c2 in zip(dim_cust_1, dim_cust_2):
                assert c1[0] == c2[0]  # Exact match on unified_customer_id
                assert c1[1] == c2[1]  # Exact match on first_name
                assert c1[2] == c2[2]  # Exact match on last_name

            # 3. Check duplicate keys in DuckDB
            dup_cust = conn2.execute("SELECT COUNT(*) - COUNT(DISTINCT unified_customer_id) FROM dim_unified_customer").fetchone()[0]
            assert dup_cust == 0
        finally:
            conn2.close()
