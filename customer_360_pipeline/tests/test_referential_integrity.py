"""
Referential integrity automated test.
Tests orphan accounts, orphan orders, and orphan interactions,
verifying that records with invalid foreign keys are cleanly isolated to quarantine.
"""

import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline


def test_referential_integrity_orphans_quarantined():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        # 1 valid customer
        customers_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_REAL_01",
                "first_name": "Valid",
                "last_name": "Parent",
                "email": "valid.parent@example.com",
                "phone": "555-0199",
                "address_line1": "100 Broadway",
                "city": "New York",
                "state": "NY",
                "postal_code": "10001",
                "country": "USA",
                "tax_id": "999-88-7777",
                "date_of_birth": "1980-01-01",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            }
        ])
        customers_df.to_csv(in_dir / "customers.csv", index=False)

        # 1 valid account and 1 orphan account
        accounts_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "account_id": "ACC_VALID_01",
                "source_customer_id": "C_REAL_01",
                "account_number": "ACT-V-100",
                "account_type": "CHECKING",
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 1000.0,
                "opened_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            {
                "source_system": "CRM_NA",
                "account_id": "ACC_ORPHAN_99",
                "source_customer_id": "NON_EXISTENT_CUST_XYZ",  # ORPHAN!
                "account_number": "ACT-O-999",
                "account_type": "SAVINGS",
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 500.0,
                "opened_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        accounts_df.to_csv(in_dir / "accounts.csv", index=False)

        # 1 valid order and 1 orphan order
        orders_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "order_id": "ORD_VALID_01",
                "account_id": "ACC_VALID_01",
                "source_customer_id": "C_REAL_01",
                "order_timestamp": "2022-06-01T10:00:00Z",
                "total_amount": 150.0,
                "currency": "USD",
                "status": "COMPLETED",
                "item_count": 2,
                "payment_method": "CREDIT_CARD",
                "source_updated_at": "2022-06-01T10:00:00Z",
            },
            {
                "source_system": "CRM_NA",
                "order_id": "ORD_ORPHAN_99",
                "account_id": "NON_EXISTENT_ACC_ABC",  # ORPHAN!
                "source_customer_id": "C_REAL_01",
                "order_timestamp": "2022-06-01T10:00:00Z",
                "total_amount": 300.0,
                "currency": "USD",
                "status": "COMPLETED",
                "item_count": 1,
                "payment_method": "CREDIT_CARD",
                "source_updated_at": "2022-06-01T10:00:00Z",
            },
        ])
        orders_df.to_csv(in_dir / "orders.csv", index=False)

        # 1 valid interaction and 1 orphan interaction
        interactions_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "interaction_id": "INT_VALID_01",
                "source_customer_id": "C_REAL_01",
                "account_id": "ACC_VALID_01",
                "interaction_timestamp": "2022-06-02T10:00:00Z",
                "channel": "CHAT",
                "interaction_type": "INQUIRY",
                "sentiment_score": 0.5,
                "resolution_status": "RESOLVED",
                "duration_seconds": 120,
                "notes": "Valid interaction",
            },
            {
                "source_system": "CRM_NA",
                "interaction_id": "INT_ORPHAN_99",
                "source_customer_id": "NON_EXISTENT_CUST_XYZ",  # ORPHAN!
                "account_id": "",
                "interaction_timestamp": "2022-06-02T10:00:00Z",
                "channel": "EMAIL",
                "interaction_type": "COMPLAINT",
                "sentiment_score": -0.8,
                "resolution_status": "OPEN",
                "duration_seconds": 60,
                "notes": "Orphan interaction",
            },
        ])
        interactions_df.to_csv(in_dir / "interactions.csv", index=False)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_ri.duckdb"

        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_RI_RUN",
            duckdb_path=str(db_path),
        )

        assert result.metrics.total_quarantined_rows == 3

        conn = duckdb.connect(str(db_path))
        try:
            q_rows = conn.execute("SELECT source_record_id, rejection_category FROM quarantine_rejected_records").fetchall()
            q_map = {r[0]: r[1] for r in q_rows}

            assert "ACC_ORPHAN_99" in q_map
            assert q_map["ACC_ORPHAN_99"] == "REFERENTIAL_INTEGRITY_VIOLATION"

            assert "ORD_ORPHAN_99" in q_map
            assert q_map["ORD_ORPHAN_99"] == "REFERENTIAL_INTEGRITY_VIOLATION"

            assert "INT_ORPHAN_99" in q_map
            assert q_map["INT_ORPHAN_99"] == "REFERENTIAL_INTEGRITY_VIOLATION"

            # Check that valid records exist in target
            acc_cnt = conn.execute("SELECT COUNT(*) FROM dim_account_unified").fetchone()[0]
            ord_cnt = conn.execute("SELECT COUNT(*) FROM fct_order_unified").fetchone()[0]
            int_cnt = conn.execute("SELECT COUNT(*) FROM fct_interaction_unified").fetchone()[0]

            assert acc_cnt == 1
            assert ord_cnt == 1
            assert int_cnt == 1
        finally:
            conn.close()
