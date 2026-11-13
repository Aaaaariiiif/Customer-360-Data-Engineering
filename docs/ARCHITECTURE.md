# Customer 360 & Entity Resolution Architecture

## 1. System Overview

The **Customer 360 Unified View & Entity Resolution Pipeline** ingests heterogeneous customer, account, order, and interaction data from disparate source systems (CRM, Core Billing, Web Store, and Support Desks), reconciles identities using strict, deterministic multi-tiered rules, isolates data quality defects into a dead-letter quarantine store, and constructs a unified Customer 360 golden master record with complete source-to-target lineage.

```mermaid
flowchart TD
    subgraph Sources ["Upstream Source Systems"]
        S1["CRM North America<br/>(Customers, Orders, Interactions)"]
        S2["CRM Europe<br/>(Customers)"]
        S3["Core Billing<br/>(Accounts, Customers)"]
        S4["Web Store<br/>(Customers, Accounts, Orders)"]
        S5["Support Desk<br/>(Interactions)"]
    end

    subgraph Ingestion ["Ingestion & Schema Contracts"]
        ING["Ingestion Engine<br/>- File format abstraction (CSV, JSON, Parquet)<br/>- Schema conformity enforcement<br/>- Ingestion metadata tagging (_run_id, _ingested_at)"]
    end

    subgraph Validation ["Data Quality & Quarantine Engine"]
        VAL["Topological Validator<br/>1. Format & Range Checks (regex, dates, numerics)<br/>2. Mandatory Field Validation<br/>3. In-Batch Duplicate Handling<br/>4. Cross-Table Referential Integrity"]
        QRN[("quarantine_rejected_records<br/>Dead-Letter Store<br/>(Raw JSON + Error Reasons)")]
    end

    subgraph EntityResolution ["Deterministic Entity Resolution"]
        NORM["Normalization & Standardization<br/>(Phone E.164, Lowercase Email, Clean Address)"]
        BLOCK["Hash-Partitioned Blocking<br/>O(N) candidate generation on (Tax, Email, Phone, Zip)"]
        RULES["Deterministic Precedence Rules<br/>Tier 1: Exact Tax ID (1.00)<br/>Tier 2: Exact Email (0.98)<br/>Tier 3: Exact Phone + Last Name (0.92)<br/>Tier 4: Exact Name + Address (0.88)"]
        DISJ["Disjoint-Set (Union-Find)<br/>Transitive Graph Clustering"]
        SURV["Deterministic Survivorship<br/>Priority: CRM > Billing > Web > Support<br/>Recency: latest source_updated_at"]
        UNC[("uncertain_matches_review<br/>Human Review Queue<br/>(Shared phones, Households)")]
    end

    subgraph Transformation ["Feature Store & Dimensional Layer"]
        XFORM["Customer 360 Transformer<br/>- Account-to-Customer linking<br/>- Order & Interaction linkage<br/>- Behavioral & Financial Aggregates<br/>- Customer Segmentation (VIP, Regular, At-Risk)"]
    end

    subgraph Storage ["Target Analytical Storage Layer"]
        DUCK[("DuckDB Database<br/>customer_360.duckdb<br/>(ACID Transactions)")]
        PQT["Columnar Parquet Store<br/>data/output/parquet/"]
        CSV["Operational CSV Exports<br/>data/output/"]
    end

    subgraph Observability ["Observability & Reconciliation"]
        RECON["Reconciliation Engine<br/>- Volume conservation<br/>- Referential integrity assertions<br/>- Financial revenue balance<br/>- Ground truth precision/recall"]
        AUDIT[("pipeline_run_audit<br/>Audit Ledger Table<br/>(Run timings, row tallies, status)")]
    end

    Sources --> ING
    ING --> VAL
    VAL -->|Malformed / Orphan Records| QRN
    VAL -->|Clean Valid Records| NORM
    NORM --> BLOCK --> RULES --> DISJ --> SURV
    RULES -->|Ambiguous Pairs| UNC
    SURV --> XFORM
    XFORM --> DUCK & PQT & CSV
    DUCK --> RECON --> AUDIT
```

---

## 2. Entity-Relationship Data Model

The target schema consists of a Conformed Customer 360 Star/Snowflake model backed by master dimensions, unified fact tables, and complete identity lineage mappings:

```mermaid
erDiagram
    dim_unified_customer ||--o{ bridge_customer_source_map : "links to source lineage"
    dim_unified_customer ||--o{ dim_account_unified : "owns"
    dim_unified_customer ||--o{ fct_order_unified : "places"
    dim_unified_customer ||--o{ fct_interaction_unified : "engages in"
    dim_unified_customer ||--|| fact_customer_360_summary : "roll-up features"

    dim_unified_customer {
        string unified_customer_id PK "UC_<sha256_hash>"
        string match_cluster_id "CLU_<sha256_hash>"
        string golden_first_name
        string golden_last_name
        string golden_email
        string golden_phone
        string primary_address
        string primary_postal_code
        string date_of_birth
        string tax_id
        int source_record_count
        float confidence_score
        string primary_source_system
        timestamp created_at
        timestamp updated_at
        string run_id
    }

    bridge_customer_source_map {
        string mapping_id PK "MAP_<md5_hash>"
        string unified_customer_id FK
        string source_system
        string source_customer_id
        string match_rule_applied
        float match_confidence
        boolean is_uncertain
        timestamp source_created_at
        timestamp source_updated_at
        timestamp ingested_at
        string run_id
    }

    dim_account_unified {
        string account_id PK
        string unified_customer_id FK
        string source_system
        string source_customer_id
        string account_number
        string account_type
        string status
        string currency
        float balance
        timestamp opened_at
        string run_id
    }

    fct_order_unified {
        string order_id PK
        string unified_customer_id FK
        string account_id FK
        string source_system
        timestamp order_timestamp
        float total_amount
        string currency
        string status
        int item_count
        string payment_method
        string run_id
    }

    fct_interaction_unified {
        string interaction_id PK
        string unified_customer_id FK
        string account_id FK
        string source_system
        timestamp interaction_timestamp
        string channel
        string interaction_type
        float sentiment_score
        string resolution_status
        int duration_seconds
        string run_id
    }

    fact_customer_360_summary {
        string unified_customer_id PK
        int total_accounts
        int active_accounts
        int lifetime_order_count
        int completed_order_count
        float lifetime_spend_usd
        float average_order_value_usd
        timestamp first_order_timestamp
        timestamp last_order_timestamp
        int total_interactions
        int open_tickets_count
        float avg_sentiment_score
        timestamp last_interaction_timestamp
        string customer_segment
        timestamp last_computed_at
        string run_id
    }

    quarantine_rejected_records {
        string quarantine_id PK
        string run_id
        string source_table
        string source_record_id
        string source_system
        string rejection_category
        string rejection_reason
        text raw_record_json
        timestamp quarantined_at
    }

    uncertain_matches_review {
        string review_id PK
        string run_id
        string entity_1_source
        string entity_1_id
        string entity_2_source
        string entity_2_id
        string match_heuristic
        float similarity_score
        string review_status
        timestamp flagged_at
    }

    pipeline_run_audit {
        string run_id PK
        string batch_id
        string status
        timestamp start_time
        timestamp end_time
        float duration_seconds
        int total_input_rows
        int total_valid_rows
        int total_quarantined_rows
        int total_golden_customers
        int total_uncertain_matches
        text input_counts_json
        text valid_counts_json
        text quarantined_counts_json
        text target_counts_json
        text error_message
    }
```

---

## 3. Core Architectural Modules

### 3.1 Data Ingestion (`src/ingestion.py`)
- Ingests raw data files across CSV, JSON/JSONL, and Parquet.
- Enforces baseline schema requirements: ensures mandatory source columns are present and fills non-existent optional columns with empty defaults.
- Handles empty batches (0-byte files or header-only files) gracefully without terminating or raising unhandled exceptions.
- Injects lineage metadata columns into all ingested records:
  - `_source_file`: Original filename.
  - `_ingested_at`: UTC timestamp of pipeline ingestion.
  - `_run_id`: Execution run identifier.

### 3.2 Data Validation & Quarantine (`src/validation.py`)
Data quality validation is executed topologially:
1. **Customers**:
   - Mandatory field validation (`source_system`, `source_customer_id`, `first_name`, `last_name`).
   - Contactability check: at least one of `email`, `phone`, or `tax_id` must be present.
   - Format validation: RFC-compliant email regex syntax check.
   - In-batch duplicate handling: identical duplicate records are deduplicated idempotently; conflicting records for the same key are routed to quarantine as `DUPLICATE_KEY_CONFLICT`.
2. **Accounts**:
   - Mandatory field checks (`account_id`, `account_type`, `status`, `currency`).
   - Referential integrity: `source_customer_id` must exist in valid customers. Orphan accounts are isolated to quarantine with `REFERENTIAL_INTEGRITY_VIOLATION`.
3. **Orders**:
   - Timestamp format check (ISO-8601 validation).
   - Referential integrity: `account_id` must exist in valid accounts. Orphan orders are quarantined.
   - Numeric validation: parseable `total_amount` float.
4. **Interactions**:
   - Timestamp format check.
   - Value range check: `sentiment_score` must fall within `[-1.0, +1.0]`. Out-of-bounds values are quarantined.
   - Referential integrity: `source_customer_id` must exist in valid customers.

All quarantined records are persisted in `quarantine_rejected_records` with the complete unedited raw row serialized in JSON, enabling operators to diagnose defects and reprocess corrections.

### 3.3 Deterministic Entity Resolution (`src/entity_resolution.py`)
To achieve industrial-scale deduplication while strictly avoiding false positives, the pipeline employs a deterministic multi-tiered matching engine:

1. **Normalization**:
   - Emails: lowercased, whitespace trimmed.
   - Phones: stripped of formatting characters to E.164-compatible national digits.
   - Addresses: lowercased, standard postal abbreviations mapped (`st` -> `street`, `ave` -> `avenue`, `dr` -> `drive`).
   - Tax IDs: stripped of punctuation and hyphens.
2. **Hash-Partitioned Candidate Blocking**:
   - Naive pairwise comparison scales as $O(N^2)$, requiring over 625 million comparisons for 25,000 records.
   - The engine partitions records into hash blocks on `tax_id`, `email`, `phone`, and `(soundex/last_name, postal_code)`.
   - Matching is only evaluated within candidate blocks, reducing runtime to $O(N)$ (under 1 second).
3. **Deterministic Precedence Rules**:
   - **Tier 1 (`RULE_EXACT_TAX_ID`, Confidence 1.00)**: Identical normalized national tax ID.
   - **Tier 2 (`RULE_EXACT_EMAIL`, Confidence 0.98)**: Identical normalized email address.
   - **Tier 3 (`RULE_EXACT_PHONE_AND_LAST_NAME`, Confidence 0.92)**: Identical normalized phone AND matching last name.
   - **Tier 4 (`RULE_EXACT_NAME_AND_ADDRESS`, Confidence 0.88)**: Identical full name AND normalized street address + postal code.
4. **Disjoint-Set (Union-Find) Graph Clustering**:
   - Matches discovered by rules form edges in an undirected identity graph.
   - Disjoint-set data structure with path compression resolves connected components into master customer clusters.
   - Transitive identity linkage is preserved (e.g. if A matches B on Tax ID and B matches C on Email, A, B, and C merge into a single golden identity).
5. **Deterministic Golden Customer ID Generation**:
   - The canonical seed is the lexicographically lowest `(source_system, source_customer_id)` in the cluster.
   - Master ID is minted as: `unified_customer_id = 'UC_' + sha256(canonical_seed)[:16]`.
   - Rerunning the pipeline on identical data always produces identical master keys.
6. **Deterministic Attribute Survivorship**:
   - Evaluated across source system priority: CRM (1) > Billing (2) > Web Store (3) > Support (4).
   - Recency: If sources have equal priority, the record with the latest `source_updated_at` takes precedence.
   - Non-null coalescing: If the winning record has a null field, the engine cascades down to the next ranked non-null value.

### 3.4 Uncertain Match Detection & Review Queue
When pairs exhibit ambiguous similarity, the engine **flags them for human review and deliberately prevents merging**:
- **`UNCERTAIN_SHARED_PHONE_DIFFERENT_NAME`**: Same phone number but different last names (e.g. roommates or family members sharing a landline).
- **`UNCERTAIN_SAME_ADDRESS_DIFFERENT_FIRST_NAME`**: Same address and last name, but different first names (e.g. parent and child).
- **`UNCERTAIN_HIGH_NAME_SIMILARITY_SAME_ZIP`**: Same postal code with high string similarity on name (0.70 to 0.87), but distinct emails/phones.

Flagged pairs are written to `uncertain_matches_review` with similarity scores, candidate profiles, and status `PENDING_REVIEW`.

### 3.5 Customer 360 Feature Store & Transformation (`src/transformation.py`)
Enriches accounts, orders, and interactions with parent `unified_customer_id` and computes behavioral aggregates:
- Financial Metrics: `lifetime_order_count`, `completed_order_count`, `lifetime_spend_usd`, `average_order_value_usd`.
- Engagement Metrics: `total_interactions`, `open_tickets_count`, `avg_sentiment_score`, `last_interaction_timestamp`.
- Customer Segmentation:
  - `VIP`: Lifetime completed spend >= $1,000 and completed orders >= 2.
  - `HIGH_VALUE`: Lifetime spend >= $500.
  - `AT_RISK`: Open support tickets >= 2 or negative average sentiment (< -0.2).
  - `REGULAR`: Active customer with completed orders.
  - `PROSPECT`: Account holder with 0 completed orders.

### 3.6 Target Storage & Idempotency (`src/storage.py`)
- Employs DuckDB as the embedded ACID analytical engine and PyArrow for Columnar Parquet exports.
- **Idempotency Strategy**:
  - In `overwrite` mode: atomically truncates and replaces tables inside `BEGIN TRANSACTION ... COMMIT`.
  - In `upsert` mode: deletes existing records matching `run_id` before inserting new rows.
  - Re-running the pipeline on identical input produces identical row counts, identical golden keys, and zero duplicate rows.

### 3.7 Automated Reconciliation & Audit (`src/reconciliation.py`)
Executes automated integrity checks on target tables:
1. **Conservation of Customer Lineage**: Total valid customers == total rows in `bridge_customer_source_map`.
2. **Volume Accounting**: Input rows == valid rows + quarantined rows + in-batch duplicates dropped.
3. **Target Referential Integrity**: Zero orphan records in `dim_account_unified`, `fct_order_unified`, or `fct_interaction_unified`.
4. **Financial Reconciliation**: Sum of completed order totals == sum of customer 360 `lifetime_spend_usd`.
5. **Target Primary Key Uniqueness**: Zero duplicate keys in `dim_unified_customer` and `fact_customer_360_summary`.
6. **Uncertain Matches Isolation**: Validates that no flagged uncertain pairs were inadvertently merged.
7. **Ground Truth Clustering Accuracy**: Verifies accuracy against ground-truth labels.
