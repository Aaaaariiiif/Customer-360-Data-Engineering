"""
Malformed input and format validation automated test.
Verifies that invalid timestamps, emails, out-of-bounds values, and corrupted
numerics are safely quarantined with full raw JSON and reason diagnostics.
"""

import json
import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline
from src.schemas import (
    SOURCE_CUSTOMER_COLUMNS,
    SOURCE_ACCOUNT_COLUMNS,
    SOURCE_ORDER_COLUMNS,
    SOURCE_INTERACTION_COLUMNS,
)


def test_malformed_records_routed_to_quarantine():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        # 1. Malformed Customer: Invalid Email
        customers_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_VALID_1",
                "first_name": "Valid",
                "last_name": "User",
                "email": "valid.user@example.com",
                "phone": "555-1234567",
                "address_line1": "100 Main St",
                "city": "Denver",
                "state": "CO",
                "postal_code": "80201",
                "country": "USA",
                "tax_id": "111-22-3333",
                "date_of_birth": "1990-01-01",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_BAD_EMAIL",
                "first_name": "Bad",
                "last_name": "Email",
                "email": "invalid_email_without_at_sign",  # MALFORMED!
                "phone": "555-9999999",
                "address_line1": "100 Main St",
                "city": "Denver",
                "state": "CO",
                "postal_code": "80201",
                "country": "USA",
                "tax_id": "",
                "date_of_birth": "1990-01-01",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        customers_df.to_csv(in_dir / "customers.csv", index=False)

        # Valid Account
        accounts_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "account_id": "ACC_1",
                "source_customer_id": "C_VALID_1",
                "account_number": "ACT-100",
                "account_type": "CHECKING",
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 100.0,
                "opened_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            }
        ])
        accounts_df.to_csv(in_dir / "accounts.csv", index=False)

        # 2. Malformed Order: Invalid Timestamp
        orders_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "order_id": "ORD_BAD_TIME",
                "account_id": "ACC_1",
                "source_customer_id": "C_VALID_1",
                "order_timestamp": "THIS_IS_NOT_A_TIMESTAMP",  # MALFORMED!
                "total_amount": 50.0,
                "currency": "USD",
                "status": "COMPLETED",
                "item_count": 1,
                "payment_method": "CREDIT_CARD",
                "source_updated_at": "2022-01-01T00:00:00Z",
            }
        ])
        orders_df.to_csv(in_dir / "orders.csv", index=False)

        # 3. Malformed Interaction: Out of Bounds Sentiment (999.0)
        interactions_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "interaction_id": "INT_BAD_SENT",
                "source_customer_id": "C_VALID_1",
                "account_id": "ACC_1",
                "interaction_timestamp": "2022-01-01T00:00:00Z",
                "channel": "CHAT",
                "interaction_type": "INQUIRY",
                "sentiment_score": 999.0,  # OUT OF BOUNDS!
                "resolution_status": "RESOLVED",
                "duration_seconds": 60,
                "notes": "Testing sentiment score out of range",
            }
        ])
        interactions_df.to_csv(in_dir / "interactions.csv", index=False)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_malformed.duckdb"

        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_MALFORMED_RUN",
            duckdb_path=str(db_path),
        )

        assert result.metrics.total_quarantined_rows == 3

        conn = duckdb.connect(str(db_path))
        try:
            q_rows = conn.execute("SELECT source_table, source_record_id, rejection_category, rejection_reason FROM quarantine_rejected_records").fetchall()
            q_map = {r[1]: (r[0], r[2], r[3]) for r in q_rows}

            assert "C_BAD_EMAIL" in q_map
            assert q_map["C_BAD_EMAIL"][1] == "MALFORMED_INPUT"
            assert "Invalid email format" in q_map["C_BAD_EMAIL"][2]

            assert "ORD_BAD_TIME" in q_map
            assert q_map["ORD_BAD_TIME"][1] == "MALFORMED_INPUT"
            assert "Invalid ISO-8601" in q_map["ORD_BAD_TIME"][2]

            assert "INT_BAD_SENT" in q_map
            assert q_map["INT_BAD_SENT"][1] == "OUT_OF_BOUNDS_VALUE"
            assert "outside valid range" in q_map["INT_BAD_SENT"][2]
        finally:
            conn.close()
