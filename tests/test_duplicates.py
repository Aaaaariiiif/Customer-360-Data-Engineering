"""
Duplicate key handling automated test.
Tests both identical duplicate deduplication (idempotent skip)
and conflicting duplicate keys (quarantined with DUPLICATE_KEY_CONFLICT).
"""

import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline


def test_in_batch_duplicates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        customers_df = pd.DataFrame([
            # Base record 1
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_DUP_1",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "phone": "555-0100",
                "address_line1": "123 Elm St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "111-00-1111",
                "date_of_birth": "1985-05-15",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            # Exact duplicate of record 1 (should be skipped idempotently)
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_DUP_1",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "phone": "555-0100",
                "address_line1": "123 Elm St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "111-00-1111",
                "date_of_birth": "1985-05-15",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            # Base record 2
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_CONFLICT_2",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
                "phone": "555-0200",
                "address_line1": "456 Oak St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "222-00-2222",
                "date_of_birth": "1990-08-20",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            # Conflicting duplicate of record 2 (different name and email!)
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_CONFLICT_2",
                "first_name": "Imposter",  # Conflict!
                "last_name": "Different",
                "email": "imposter@scam.org",
                "phone": "555-0200",
                "address_line1": "456 Oak St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "222-00-2222",
                "date_of_birth": "1990-08-20",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        customers_df.to_csv(in_dir / "customers.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "accounts.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "orders.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "interactions.csv", index=False)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_dups.duckdb"

        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_DUPS_RUN",
            duckdb_path=str(db_path),
        )

        # We had 4 input customers:
        # - 1 valid C_DUP_1
        # - 1 identical duplicate skipped
        # - 1 valid C_CONFLICT_2
        # - 1 conflicting duplicate quarantined
        assert result.metrics.total_input_rows == 4
        assert result.metrics.total_valid_rows == 2
        assert result.metrics.total_quarantined_rows == 1

        conn = duckdb.connect(str(db_path))
        try:
            q_row = conn.execute("SELECT source_record_id, rejection_category FROM quarantine_rejected_records").fetchone()
            assert q_row is not None
            assert q_row[0] == "C_CONFLICT_2"
            assert q_row[1] == "DUPLICATE_KEY_CONFLICT"

            # Check that only 2 golden customers exist
            golden_count = conn.execute("SELECT COUNT(*) FROM dim_unified_customer").fetchone()[0]
            assert golden_count == 2
        finally:
            conn.close()
