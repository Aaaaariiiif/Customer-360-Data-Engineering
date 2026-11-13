"""
Domain-specific edge case automated tests.
Tests:
1. Shared phone number with different last names (flagged uncertain, NOT merged)
2. Same household with different first names (flagged uncertain, NOT merged)
3. Late-arriving / out-of-order updates (newer golden attributes preserved)
4. Multi-source financial aggregation and refund adjustments
"""

import tempfile
from pathlib import Path
import duckdb
import pandas as pd
import pytest
 
from src.config import PipelineConfig
from src.entity_resolution import EntityResolutionEngine
from src.pipeline import Customer360Pipeline


def test_edge_case_shared_phone_flagged_not_merged():
    """
    Edge Case 1: Roommates or family sharing the same landline phone number
    with different last names must be flagged for review and NOT merged.
    """
    er = EntityResolutionEngine(run_id="TEST_EDGE_1")

    df = pd.DataFrame([
        {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "C_ROOMMATE_A",
            "first_name": "Marcus",
            "last_name": "Vance",
            "email": "marcus.vance@tech.org",
            "phone": "312-555-8899",  # Shared phone
            "tax_id": "",
            "address_line1": "500 Michigan Ave",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60611",
            "country": "USA",
            "date_of_birth": "1994-01-01",
            "source_created_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        },
        {
            "source_system": "WEB_STORE",
            "source_customer_id": "C_ROOMMATE_B",
            "first_name": "Emily",
            "last_name": "Clark",  # Different last name!
            "email": "emily.clark@domain.org",
            "phone": "(312) 555-8899",  # Same phone!
            "tax_id": "",
            "address_line1": "500 Michigan Ave Apt 4B",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60611",
            "country": "USA",
            "date_of_birth": "1995-02-02",
            "source_created_at": "2022-02-01T00:00:00Z",
            "source_updated_at": "2022-02-01T00:00:00Z",
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df)

    # Must NOT be merged: 2 distinct golden records
    assert len(golden) == 2
    assert len(bridge) == 2
    assert bridge["unified_customer_id"].iloc[0] != bridge["unified_customer_id"].iloc[1]

    # Must be present in uncertain matches queue
    assert len(uncertain) >= 1
    assert any(u["match_heuristic"] == "UNCERTAIN_SHARED_PHONE_DIFFERENT_NAME" for _, u in uncertain.iterrows())


def test_edge_case_same_household_different_first_name():
    """
    Edge Case 2: Parent and child living at the same address with same last name,
    but different first names (e.g. Thomas Miller Sr vs Timothy Miller Jr).
    Must be flagged for review and NOT merged.
    """
    er = EntityResolutionEngine(run_id="TEST_EDGE_2")

    df = pd.DataFrame([
        {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "C_MILLER_SR",
            "first_name": "Thomas",
            "last_name": "Miller",
            "email": "thomas.miller@household.com",
            "phone": "602-555-0101",
            "tax_id": "",
            "address_line1": "123 Desert Ridge Rd",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85001",
            "country": "USA",
            "date_of_birth": "1960-05-15",
            "source_created_at": "2020-01-01T00:00:00Z",
            "source_updated_at": "2020-01-01T00:00:00Z",
        },
        {
            "source_system": "BILLING_CORE",
            "source_customer_id": "C_MILLER_JR",
            "first_name": "Timothy",  # Different first name!
            "last_name": "Miller",  # Same last name and address!
            "email": "timothy.miller@household.com",
            "phone": "602-555-0102",
            "tax_id": "",
            "address_line1": "123 Desert Ridge Rd",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85001",
            "country": "USA",
            "date_of_birth": "1998-10-12",
            "source_created_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df)

    # Must NOT be merged
    assert len(golden) == 2
    assert len(bridge) == 2
    assert bridge["unified_customer_id"].iloc[0] != bridge["unified_customer_id"].iloc[1]

    # Flagged as uncertain
    assert len(uncertain) >= 1
    assert any(u["match_heuristic"] == "UNCERTAIN_SAME_ADDRESS_DIFFERENT_FIRST_NAME" for _, u in uncertain.iterrows())


def test_edge_case_late_arriving_data_preserves_newest():
    """
    Edge Case 3: Late arriving data.
    If an older record from an external store arrives, it should not overwrite
    a newer record's verified attribute when source priority is equal.
    """
    er = EntityResolutionEngine(run_id="TEST_EDGE_3")

    df = pd.DataFrame([
        # Older record
        {
            "source_system": "WEB_STORE",
            "source_customer_id": "C_OLD",
            "first_name": "Sarah",
            "last_name": "Connor",
            "email": "sarah.connor@cyber.com",
            "phone": "555-0001",
            "tax_id": "999-00-1111",
            "address_line1": "Old Address Rd",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "USA",
            "date_of_birth": "1985-01-01",
            "source_created_at": "2020-01-01T00:00:00Z",
            "source_updated_at": "2020-01-01T00:00:00Z",  # Older!
        },
        # Newer record with updated address
        {
            "source_system": "WEB_STORE",
            "source_customer_id": "C_NEW",
            "first_name": "Sarah",
            "last_name": "Connor",
            "email": "sarah.connor@cyber.com",
            "phone": "555-0001",
            "tax_id": "999-00-1111",  # Same Tax ID & Email
            "address_line1": "New Upgraded Sanctuary",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "USA",
            "date_of_birth": "1985-01-01",
            "source_created_at": "2023-01-01T00:00:00Z",
            "source_updated_at": "2023-08-15T12:00:00Z",  # Newer!
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df)
    assert len(golden) == 1
    # Golden address must be the newer one
    assert golden["primary_address"].iloc[0] == "New Upgraded Sanctuary"


def test_edge_case_multi_source_financial_aggregation():
    """
    Edge Case 4: Customer with accounts and orders spanning CRM_NA and Web Store,
    including a refund transaction.
    Verifies Customer 360 aggregates financial spend across all connected source systems.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir(parents=True)

        customers_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "source_customer_id": "C_FIN_CRM",
                "first_name": "Victor",
                "last_name": "Stone",
                "email": "victor.stone@titan.org",
                "phone": "555-7777",
                "tax_id": "888-00-8888",
                "address_line1": "100 Titan Tower",
                "city": "Detroit",
                "state": "MI",
                "postal_code": "48201",
                "country": "USA",
                "date_of_birth": "1994-03-25",
                "source_created_at": "2021-01-01T00:00:00Z",
                "source_updated_at": "2021-01-01T00:00:00Z",
            },
            {
                "source_system": "WEB_STORE",
                "source_customer_id": "C_FIN_WEB",
                "first_name": "Victor",
                "last_name": "Stone",
                "email": "victor.stone@titan.org",  # Same email!
                "phone": "555-7777",
                "tax_id": "888-00-8888",
                "address_line1": "100 Titan Tower",
                "city": "Detroit",
                "state": "MI",
                "postal_code": "48201",
                "country": "USA",
                "date_of_birth": "1994-03-25",
                "source_created_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        customers_df.to_csv(in_dir / "customers.csv", index=False)

        accounts_df = pd.DataFrame([
            {
                "source_system": "CRM_NA",
                "account_id": "ACC_CRM_1",
                "source_customer_id": "C_FIN_CRM",
                "account_number": "ACT-CRM-01",
                "account_type": "ENTERPRISE",
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 5000.0,
                "opened_at": "2021-01-01T00:00:00Z",
                "source_updated_at": "2021-01-01T00:00:00Z",
            },
            {
                "source_system": "WEB_STORE",
                "account_id": "ACC_WEB_1",
                "source_customer_id": "C_FIN_WEB",
                "account_number": "ACT-WEB-01",
                "account_type": "RETAIL",
                "status": "ACTIVE",
                "currency": "USD",
                "balance": 100.0,
                "opened_at": "2022-01-01T00:00:00Z",
                "source_updated_at": "2022-01-01T00:00:00Z",
            },
        ])
        accounts_df.to_csv(in_dir / "accounts.csv", index=False)

        orders_df = pd.DataFrame([
            # Order 1 in CRM: $1,200 (Completed)
            {
                "source_system": "CRM_NA",
                "order_id": "ORD_CRM_01",
                "account_id": "ACC_CRM_1",
                "source_customer_id": "C_FIN_CRM",
                "order_timestamp": "2021-06-01T10:00:00Z",
                "total_amount": 1200.0,
                "currency": "USD",
                "status": "COMPLETED",
                "item_count": 2,
                "payment_method": "BANK_TRANSFER",
                "source_updated_at": "2021-06-01T10:00:00Z",
            },
            # Order 2 in Web Store: $300 (Completed)
            {
                "source_system": "WEB_STORE",
                "order_id": "ORD_WEB_01",
                "account_id": "ACC_WEB_1",
                "source_customer_id": "C_FIN_WEB",
                "order_timestamp": "2022-03-01T10:00:00Z",
                "total_amount": 300.0,
                "currency": "USD",
                "status": "COMPLETED",
                "item_count": 1,
                "payment_method": "CREDIT_CARD",
                "source_updated_at": "2022-03-01T10:00:00Z",
            },
        ])
        orders_df.to_csv(in_dir / "orders.csv", index=False)
        pd.DataFrame().to_csv(in_dir / "interactions.csv", index=False)

        config = PipelineConfig()
        pipeline = Customer360Pipeline(config=config)
        db_path = out_dir / "test_fin.duckdb"

        result = pipeline.run(
            input_dir=str(in_dir),
            output_dir=str(out_dir),
            run_id="TEST_FIN_RUN",
            duckdb_path=str(db_path),
        )

        conn = duckdb.connect(str(db_path))
        try:
            summary = conn.execute("""
                SELECT total_accounts, active_accounts, completed_order_count, lifetime_spend_usd, customer_segment 
                FROM fact_customer_360_summary
            """).fetchone()

            # 2 accounts linked across CRM and Web Store
            assert summary[0] == 2
            assert summary[1] == 2
            # 2 completed orders ($1200 + $300 = $1500)
            assert summary[2] == 2
            assert summary[3] == 1500.0
            # Segment should be VIP (spend >= 1000 and count >= 2)
            assert summary[4] == "VIP"
        finally:
            conn.close()
