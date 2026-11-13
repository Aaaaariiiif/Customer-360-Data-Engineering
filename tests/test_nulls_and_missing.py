"""
Null and missing mandatory field validation automated test.
Verifies that records missing required identifiers, names, or contactability
are isolated to quarantine with MISSING_REQUIRED_FIELD.
"""

import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline


def test_missing_required_fields_quarantined():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        customers_df = pd.DataFrame([
            # Missing first name
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_NO_FIRSTNAME",
                "first_name": "",  # MISSING!
                "last_name": "Smith",
                "email": "smith@test.com",
                "phone": "555-1234",
                "address_line1": "123 Main St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "",
                "date_of_birth": "1980-01-01",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            # Missing all contact info
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_NO_CONTACT",
                "first_name": "Ghost",
                "last_name": "User",
                "email": "",  # MISSING!
                "phone": "",  # MISSING!
                "address_line1": "123 Main St",
                "city": "Dallas",
                "state": "TX",
                "postal_code": "75201",
                "country": "USA",
                "tax_id": "",  # MISSING!
                "date_of_birth": "1980-01-01",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        customers_df.to_csv(in_dir / "customers.csv", index=False)

        accounts_df = pd.DataFrame([
            # Missing account_type
            {
                "source_system": "CRM_NA",
                "account_id": "ACC_NO_TYPE",
                "source_customer_id": "C_NO_FIRSTNAME",
                "account_number": "ACT-999",
                "account_type": "",  # MISSING!
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 50.0,
                "opened_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            }
        ])
        accounts_df.to_csv(in_dir / "accounts.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "orders.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "interactions.csv", index=False)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_missing.duckdb"

        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_MISSING_RUN",
            duckdb_path=str(db_path),
        )

        assert result.metrics.total_quarantined_rows == 3

        conn = duckdb.connect(str(db_path))
        try:
            q_recs = conn.execute("SELECT source_record_id, rejection_category FROM quarantine_rejected_records").fetchall()
            rec_map = {r[0]: r[1] for r in q_recs}
            assert "C_NO_FIRSTNAME" in rec_map
            assert rec_map["C_NO_FIRSTNAME"] == "MISSING_REQUIRED_FIELD"
            assert "C_NO_CONTACT" in rec_map
            assert rec_map["C_NO_CONTACT"] == "MISSING_REQUIRED_FIELD"
            assert "ACC_NO_TYPE" in rec_map
            assert rec_map["ACC_NO_TYPE"] == "MISSING_REQUIRED_FIELD"
        finally:
            conn.close()
