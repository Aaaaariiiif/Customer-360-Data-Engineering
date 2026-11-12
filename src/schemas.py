"""
Schema definitions for source, target, quarantine, and audit tables.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Expected Columns and Data Types for Raw Source Ingestion
# ---------------------------------------------------------------------------

SOURCE_CUSTOMER_COLUMNS = [
    "source_system",
    "source_customer_id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address_line1",
    "city",
    "state",
    "postal_code",
    "country",
    "tax_id",
    "date_of_birth",
    "source_created_at",
    "source_updated_at",
]

SOURCE_ACCOUNT_COLUMNS = [
    "source_system",
    "account_id",
    "source_customer_id",
    "account_number",
    "account_type",
    "status",
    "currency",
    "balance",
    "opened_at",
    "source_updated_at",
]

SOURCE_ORDER_COLUMNS = [
    "source_system",
    "order_id",
    "account_id",
    "source_customer_id",
    "order_timestamp",
    "total_amount",
    "currency",
    "status",
    "item_count",
    "payment_method",
    "source_updated_at",
]

SOURCE_INTERACTION_COLUMNS = [
    "source_system",
    "interaction_id",
    "source_customer_id",
    "account_id",
    "interaction_timestamp",
    "channel",
    "interaction_type",
    "sentiment_score",
    "resolution_status",
    "duration_seconds",
    "notes",
]

# ---------------------------------------------------------------------------
# Target Table Column Definitions
# ---------------------------------------------------------------------------

DIM_UNIFIED_CUSTOMER_COLUMNS = [
    "unified_customer_id",
    "match_cluster_id",
    "golden_first_name",
    "golden_last_name",
    "golden_email",
    "golden_phone",
    "primary_address",
    "primary_city",
    "primary_state",
    "primary_postal_code",
    "primary_country",
    "date_of_birth",
    "tax_id",
    "source_record_count",
    "confidence_score",
    "primary_source_system",
    "created_at",
    "updated_at",
    "run_id",
]

BRIDGE_CUSTOMER_SOURCE_MAP_COLUMNS = [
    "mapping_id",
    "unified_customer_id",
    "source_system",
    "source_customer_id",
    "match_rule_applied",
    "match_confidence",
    "is_uncertain",
    "source_created_at",
    "source_updated_at",
    "ingested_at",
    "run_id",
]

DIM_ACCOUNT_UNIFIED_COLUMNS = [
    "account_id",
    "unified_customer_id",
    "source_system",
    "source_customer_id",
    "account_number",
    "account_type",
    "status",
    "currency",
    "balance",
    "opened_at",
    "run_id",
]

FCT_ORDER_UNIFIED_COLUMNS = [
    "order_id",
    "unified_customer_id",
    "account_id",
    "source_system",
    "order_timestamp",
    "total_amount",
    "currency",
    "status",
    "item_count",
    "payment_method",
    "run_id",
]

FCT_INTERACTION_UNIFIED_COLUMNS = [
    "interaction_id",
    "unified_customer_id",
    "account_id",
    "source_system",
    "interaction_timestamp",
    "channel",
    "interaction_type",
    "sentiment_score",
    "resolution_status",
    "duration_seconds",
    "run_id",
]

FACT_CUSTOMER_360_SUMMARY_COLUMNS = [
    "unified_customer_id",
    "total_accounts",
    "active_accounts",
    "lifetime_order_count",
    "completed_order_count",
    "lifetime_spend_usd",
    "average_order_value_usd",
    "first_order_timestamp",
    "last_order_timestamp",
    "total_interactions",
    "open_tickets_count",
    "avg_sentiment_score",
    "last_interaction_timestamp",
    "customer_segment",
    "last_computed_at",
    "run_id",
]

QUARANTINE_REJECTED_RECORDS_COLUMNS = [
    "quarantine_id",
    "run_id",
    "source_table",
    "source_record_id",
    "source_system",
    "rejection_category",
    "rejection_reason",
    "raw_record_json",
    "quarantined_at",
]

UNCERTAIN_MATCHES_REVIEW_COLUMNS = [
    "review_id",
    "run_id",
    "entity_1_source",
    "entity_1_id",
    "entity_1_name",
    "entity_1_email",
    "entity_1_phone",
    "entity_2_source",
    "entity_2_id",
    "entity_2_name",
    "entity_2_email",
    "entity_2_phone",
    "match_heuristic",
    "similarity_score",
    "review_status",
    "flagged_at",
]

PIPELINE_RUN_AUDIT_COLUMNS = [
    "run_id",
    "batch_id",
    "status",
    "start_time",
    "end_time",
    "duration_seconds",
    "total_input_rows",
    "total_valid_rows",
    "total_quarantined_rows",
    "total_golden_customers",
    "total_uncertain_matches",
    "input_counts_json",
    "valid_counts_json",
    "quarantined_counts_json",
    "target_counts_json",
    "error_message",
]

# ---------------------------------------------------------------------------
# DDL Statements for DuckDB Target Database
# ---------------------------------------------------------------------------

DUCKDB_SCHEMA_DDL = {
    "dim_unified_customer": """
        CREATE TABLE IF NOT EXISTS dim_unified_customer (
            unified_customer_id VARCHAR PRIMARY KEY,
            match_cluster_id VARCHAR,
            golden_first_name VARCHAR,
            golden_last_name VARCHAR,
            golden_email VARCHAR,
            golden_phone VARCHAR,
            primary_address VARCHAR,
            primary_city VARCHAR,
            primary_state VARCHAR,
            primary_postal_code VARCHAR,
            primary_country VARCHAR,
            date_of_birth VARCHAR,
            tax_id VARCHAR,
            source_record_count INTEGER,
            confidence_score DOUBLE,
            primary_source_system VARCHAR,
            created_at VARCHAR,
            updated_at VARCHAR,
            run_id VARCHAR
        );
    """,
    "bridge_customer_source_map": """
        CREATE TABLE IF NOT EXISTS bridge_customer_source_map (
            mapping_id VARCHAR PRIMARY KEY,
            unified_customer_id VARCHAR,
            source_system VARCHAR,
            source_customer_id VARCHAR,
            match_rule_applied VARCHAR,
            match_confidence DOUBLE,
            is_uncertain BOOLEAN,
            source_created_at VARCHAR,
            source_updated_at VARCHAR,
            ingested_at VARCHAR,
            run_id VARCHAR
        );
    """,
    "dim_account_unified": """
        CREATE TABLE IF NOT EXISTS dim_account_unified (
            account_id VARCHAR PRIMARY KEY,
            unified_customer_id VARCHAR,
            source_system VARCHAR,
            source_customer_id VARCHAR,
            account_number VARCHAR,
            account_type VARCHAR,
            status VARCHAR,
            currency VARCHAR,
            balance DOUBLE,
            opened_at VARCHAR,
            run_id VARCHAR
        );
    """,
    "fct_order_unified": """
        CREATE TABLE IF NOT EXISTS fct_order_unified (
            order_id VARCHAR PRIMARY KEY,
            unified_customer_id VARCHAR,
            account_id VARCHAR,
            source_system VARCHAR,
            order_timestamp VARCHAR,
            total_amount DOUBLE,
            currency VARCHAR,
            status VARCHAR,
            item_count INTEGER,
            payment_method VARCHAR,
            run_id VARCHAR
        );
    """,
    "fct_interaction_unified": """
        CREATE TABLE IF NOT EXISTS fct_interaction_unified (
            interaction_id VARCHAR PRIMARY KEY,
            unified_customer_id VARCHAR,
            account_id VARCHAR,
            source_system VARCHAR,
            interaction_timestamp VARCHAR,
            channel VARCHAR,
            interaction_type VARCHAR,
            sentiment_score DOUBLE,
            resolution_status VARCHAR,
            duration_seconds INTEGER,
            run_id VARCHAR
        );
    """,
    "fact_customer_360_summary": """
        CREATE TABLE IF NOT EXISTS fact_customer_360_summary (
            unified_customer_id VARCHAR PRIMARY KEY,
            total_accounts INTEGER,
            active_accounts INTEGER,
            lifetime_order_count INTEGER,
            completed_order_count INTEGER,
            lifetime_spend_usd DOUBLE,
            average_order_value_usd DOUBLE,
            first_order_timestamp VARCHAR,
            last_order_timestamp VARCHAR,
            total_interactions INTEGER,
            open_tickets_count INTEGER,
            avg_sentiment_score DOUBLE,
            last_interaction_timestamp VARCHAR,
            customer_segment VARCHAR,
            last_computed_at VARCHAR,
            run_id VARCHAR
        );
    """,
    "quarantine_rejected_records": """
        CREATE TABLE IF NOT EXISTS quarantine_rejected_records (
            quarantine_id VARCHAR PRIMARY KEY,
            run_id VARCHAR,
            source_table VARCHAR,
            source_record_id VARCHAR,
            source_system VARCHAR,
            rejection_category VARCHAR,
            rejection_reason VARCHAR,
            raw_record_json VARCHAR,
            quarantined_at VARCHAR
        );
    """,
    "uncertain_matches_review": """
        CREATE TABLE IF NOT EXISTS uncertain_matches_review (
            review_id VARCHAR PRIMARY KEY,
            run_id VARCHAR,
            entity_1_source VARCHAR,
            entity_1_id VARCHAR,
            entity_1_name VARCHAR,
            entity_1_email VARCHAR,
            entity_1_phone VARCHAR,
            entity_2_source VARCHAR,
            entity_2_id VARCHAR,
            entity_2_name VARCHAR,
            entity_2_email VARCHAR,
            entity_2_phone VARCHAR,
            match_heuristic VARCHAR,
            similarity_score DOUBLE,
            review_status VARCHAR,
            flagged_at VARCHAR
        );
    """,
    "pipeline_run_audit": """
        CREATE TABLE IF NOT EXISTS pipeline_run_audit (
            run_id VARCHAR PRIMARY KEY,
            batch_id VARCHAR,
            status VARCHAR,
            start_time VARCHAR,
            end_time VARCHAR,
            duration_seconds DOUBLE,
            total_input_rows INTEGER,
            total_valid_rows INTEGER,
            total_quarantined_rows INTEGER,
            total_golden_customers INTEGER,
            total_uncertain_matches INTEGER,
            input_counts_json VARCHAR,
            valid_counts_json VARCHAR,
            quarantined_counts_json VARCHAR,
            target_counts_json VARCHAR,
            error_message VARCHAR
        );
    """,
}
