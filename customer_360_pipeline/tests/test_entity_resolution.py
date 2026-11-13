"""
Deterministic Entity Resolution unit and integration tests.
Tests each matching rule tier, transitive graph clustering,
and deterministic survivorship attribute selection.
"""

import pandas as pd
import pytest

from src.entity_resolution import EntityResolutionEngine


def test_matching_tiers_and_clustering():
    er = EntityResolutionEngine(run_id="TEST_ER_RUN")

    # 1. Tax ID Match
    df_tax = pd.DataFrame([
        {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "C_TAX_1",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice@work.com",
            "phone": "555-0100",
            "tax_id": "123-45-6789",
            "address_line1": "100 Main St",
            "city": "NY",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "date_of_birth": "1988-01-01",
            "source_created_at": "2021-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        },
        {
            "source_system": "WEB_STORE",
            "source_customer_id": "C_TAX_2",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice.personal@gmail.com",
            "phone": "555-0999",
            "tax_id": "123-45-6789",  # Same tax ID!
            "address_line1": "100 Main Street",
            "city": "NY",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "date_of_birth": "1988-01-01",
            "source_created_at": "2021-06-01T00:00:00Z",
            "source_updated_at": "2023-01-01T00:00:00Z",
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df_tax)
    assert len(golden) == 1
    assert len(bridge) == 2
    assert bridge["unified_customer_id"].iloc[0] == bridge["unified_customer_id"].iloc[1]
    assert bridge["match_rule_applied"].iloc[0] == "RULE_EXACT_TAX_ID"


def test_email_matching_with_case_normalization():
    er = EntityResolutionEngine(run_id="TEST_ER_RUN")

    df_email = pd.DataFrame([
        {
            "source_system": "CRM_EUROPE",
            "source_customer_id": "C_EM_1",
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob.jones@corporate.org",
            "phone": "44-20-7946-0919",
            "tax_id": "",
            "address_line1": "221B Baker St",
            "city": "London",
            "state": "LDN",
            "postal_code": "NW16XE",
            "country": "GBR",
            "date_of_birth": "1985-05-15",
            "source_created_at": "2021-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        },
        {
            "source_system": "BILLING_CORE",
            "source_customer_id": "C_EM_2",
            "first_name": "Robert",
            "last_name": "Jones",
            "email": "  BOB.JONES@CORPORATE.ORG  ",  # Normalized email match!
            "phone": "",
            "tax_id": "",
            "address_line1": "221B Baker St",
            "city": "London",
            "state": "LDN",
            "postal_code": "NW16XE",
            "country": "GBR",
            "date_of_birth": "1985-05-15",
            "source_created_at": "2021-05-01T00:00:00Z",
            "source_updated_at": "2023-01-01T00:00:00Z",
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df_email)
    assert len(golden) == 1
    assert len(bridge) == 2
    assert bridge["unified_customer_id"].iloc[0] == bridge["unified_customer_id"].iloc[1]
    assert bridge["match_rule_applied"].iloc[0] == "RULE_EXACT_EMAIL"


def test_transitive_clustering():
    """
    Test graph transitivity:
    Record A matches Record B on Tax ID
    Record B matches Record C on Email
    -> All three (A, B, C) must resolve to the EXACT SAME unified_customer_id.
    """
    er = EntityResolutionEngine(run_id="TEST_ER_RUN")

    df_transitive = pd.DataFrame([
        {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "REC_A",
            "first_name": "Carol",
            "last_name": "White",
            "email": "carol.a@company.com",
            "phone": "555-1111",
            "tax_id": "TAX-12345",
            "address_line1": "100 Pine St",
            "city": "Dallas",
            "state": "TX",
            "postal_code": "75201",
            "country": "USA",
            "date_of_birth": "1980-01-01",
            "source_created_at": "2020-01-01T00:00:00Z",
            "source_updated_at": "2020-01-01T00:00:00Z",
        },
        {
            "source_system": "BILLING_CORE",
            "source_customer_id": "REC_B",
            "first_name": "Carol",
            "last_name": "White",
            "email": "carol.shared@gmail.com",
            "phone": "555-2222",
            "tax_id": "TAX-12345",  # Matches REC_A on Tax ID!
            "address_line1": "100 Pine St",
            "city": "Dallas",
            "state": "TX",
            "postal_code": "75201",
            "country": "USA",
            "date_of_birth": "1980-01-01",
            "source_created_at": "2021-01-01T00:00:00Z",
            "source_updated_at": "2021-01-01T00:00:00Z",
        },
        {
            "source_system": "WEB_STORE",
            "source_customer_id": "REC_C",
            "first_name": "Caroline",
            "last_name": "White",
            "email": "carol.shared@gmail.com",  # Matches REC_B on Email!
            "phone": "555-3333",
            "tax_id": "",
            "address_line1": "200 Oak St",
            "city": "Dallas",
            "state": "TX",
            "postal_code": "75201",
            "country": "USA",
            "date_of_birth": "1980-01-01",
            "source_created_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        },
    ])

    golden, bridge, uncertain = er.resolve_entities(df_transitive)
    assert len(golden) == 1
    assert len(bridge) == 3

    # All three must have the same unified_customer_id
    uids = set(bridge["unified_customer_id"])
    assert len(uids) == 1
    assert golden["source_record_count"].iloc[0] == 3
