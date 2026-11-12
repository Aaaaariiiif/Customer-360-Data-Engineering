# Customer 360 Data Dictionary

This document defines the schemas, grains, primary/foreign keys, nullability, uniqueness, business constraints, and lineage tracking for all raw source entities, target dimensional/fact models, quarantine dead-letter tables, and operational audit logs.

---

## 1. Source Entities

### 1.1 `customers` (Raw CRM / Web Store / POS)
- **Business Description**: Raw customer profiles extracted from upstream CRM and billing systems.
- **Grain**: One record per source customer account in a given source system.
- **Natural Key**: `(source_system, source_customer_id)`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `source_system` | VARCHAR | No | Part of PK | Identifier of upstream source system (e.g. `CRM_NORTH_AMERICA`, `WEB_STORE`). |
| `source_customer_id` | VARCHAR | No | Part of PK | Primary identifier within the source system. |
| `first_name` | VARCHAR | No | No | Customer legal/given name. Mandatory. |
| `last_name` | VARCHAR | No | No | Customer family/surname. Mandatory. |
| `email` | VARCHAR | Yes | No | Customer email address. Validated against RFC email regex syntax. |
| `phone` | VARCHAR | Yes | No | Customer telephone number. Standardized to E.164 stripped digit format. |
| `address_line1` | VARCHAR | Yes | No | Primary physical street address. Standardized via abbreviation mapping. |
| `city` | VARCHAR | Yes | No | City of residence. |
| `state` | VARCHAR | Yes | No | State or province code (e.g. `NY`, `CA`, `TX`). |
| `postal_code` | VARCHAR | Yes | No | Postal code / ZIP code. Normalized to 5 digits in US. |
| `country` | VARCHAR | Yes | No | Country code or country name. |
| `tax_id` | VARCHAR | Yes | No | Masked national tax identifier (SSN / TIN / National ID). Stripped of hyphens. |
| `date_of_birth` | VARCHAR | Yes | No | Date of birth in ISO `YYYY-MM-DD` format. |
| `source_created_at` | VARCHAR | Yes | No | Upstream creation timestamp in ISO-8601 format. |
| `source_updated_at` | VARCHAR | Yes | No | Upstream last modified timestamp in ISO-8601 format. Used for survivorship. |
| `_source_file` | VARCHAR | No | No | Lineage: source filename from which row was ingested. |
| `_ingested_at` | VARCHAR | No | No | Lineage: UTC timestamp of pipeline ingestion. |
| `_run_id` | VARCHAR | No | No | Lineage: pipeline execution run ID. |

---

### 1.2 `accounts` (Core Banking / Billing / Subscription)
- **Business Description**: Financial or service accounts owned by customers.
- **Grain**: One record per account.
- **Primary Key**: `account_id`
- **Foreign Key**: `source_customer_id` -> `customers.source_customer_id`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `source_system` | VARCHAR | No | No | System originating the account record (e.g. `BILLING_CORE`). |
| `account_id` | VARCHAR | No | Yes (PK) | Unique system account identifier. |
| `source_customer_id` | VARCHAR | No | No (FK) | Reference to customer owner. Quarantined if parent customer does not exist. |
| `account_number` | VARCHAR | No | Yes | Customer-facing account number (e.g. `ACT-0001001`). |
| `account_type` | VARCHAR | No | No | Account classification (`CHECKING`, `SAVINGS`, `CREDIT`, `ENTERPRISE`, `RETAIL`). |
| `status` | VARCHAR | No | No | Operational status (`ACTIVE`, `SUSPENDED`, `CLOSED`). |
| `currency` | VARCHAR | No | No | ISO-4217 3-letter currency code (e.g. `USD`, `EUR`, `GBP`). |
| `balance` | DOUBLE | Yes | No | Current account ledger balance in specified currency. |
| `opened_at` | VARCHAR | Yes | No | Account opening timestamp in ISO-8601 format. |
| `source_updated_at` | VARCHAR | Yes | No | Last modification timestamp in ISO-8601 format. |

---

### 1.3 `orders` (E-Commerce / ERP / Sales Orders)
- **Business Description**: Commercial transaction headers placed by customers against accounts.
- **Grain**: One record per order transaction.
- **Primary Key**: `order_id`
- **Foreign Key**: `account_id` -> `accounts.account_id`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `source_system` | VARCHAR | No | No | Source channel (e.g. `WEB_STORE`, `CRM_NORTH_AMERICA`). |
| `order_id` | VARCHAR | No | Yes (PK) | Unique order reference code. |
| `account_id` | VARCHAR | No | No (FK) | Reference to parent billing account. Quarantined if orphan. |
| `source_customer_id` | VARCHAR | Yes | No | Optional direct source customer reference. |
| `order_timestamp` | VARCHAR | No | No | Transaction ISO-8601 timestamp. Validated on ingestion. |
| `total_amount` | DOUBLE | No | No | Gross transaction total. Positive for sales; negative for refunds. |
| `currency` | VARCHAR | No | No | ISO currency code. |
| `status` | VARCHAR | No | No | Order status (`COMPLETED`, `PENDING`, `CANCELLED`, `REFUNDED`). |
| `item_count` | INTEGER | No | No | Number of line items purchased (minimum 1). |
| `payment_method` | VARCHAR | Yes | No | Payment type (`CREDIT_CARD`, `PAYPAL`, `BANK_TRANSFER`, `CRYPTO`). |
| `source_updated_at` | VARCHAR | Yes | No | Upstream update timestamp. |

---

### 1.4 `interactions` (Support Desk / Omnichannel Contact Center)
- **Business Description**: Omnichannel touchpoints between customer and support teams.
- **Grain**: One record per customer interaction / service ticket.
- **Primary Key**: `interaction_id`
- **Foreign Key**: `source_customer_id` -> `customers.source_customer_id`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `source_system` | VARCHAR | No | No | System originating interaction (e.g. `SUPPORT_DESK`). |
| `interaction_id` | VARCHAR | No | Yes (PK) | Unique ticket or interaction identifier. |
| `source_customer_id` | VARCHAR | No | No (FK) | Reference to customer. Quarantined if parent customer does not exist. |
| `account_id` | VARCHAR | Yes | No | Optional account reference. |
| `interaction_timestamp` | VARCHAR | No | No | ISO-8601 touchpoint timestamp. |
| `channel` | VARCHAR | No | No | Contact channel (`CHAT`, `EMAIL`, `PHONE`, `PORTAL`). |
| `interaction_type` | VARCHAR | No | No | Reason (`INQUIRY`, `COMPLAINT`, `TECHNICAL_SUPPORT`, `BILLING`, `FEEDBACK`). |
| `sentiment_score` | DOUBLE | Yes | No | NLP sentiment score. Validated between `-1.0` and `+1.0`. |
| `resolution_status` | VARCHAR | No | No | Status (`RESOLVED`, `OPEN`, `ESCALATED`, `PENDING_USER`). |
| `duration_seconds` | INTEGER | No | No | Contact duration in seconds (>= 0). |
| `notes` | VARCHAR | Yes | No | Free-form representative agent notes. |

---

## 2. Target Analytical Model (Customer 360)

### 2.1 `dim_unified_customer` (Golden Master Customer Dimension)
- **Business Description**: Single golden record representing a resolved, unified customer identity across all connected sources.
- **Grain**: One record per unified customer entity.
- **Primary Key**: `unified_customer_id`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `unified_customer_id` | VARCHAR | No | Yes (PK) | Deterministic ID `UC_<sha256_hash>` generated from canonical cluster seed. |
| `match_cluster_id` | VARCHAR | No | No | Cluster group identifier `CLU_<sha256_hash>`. |
| `golden_first_name` | VARCHAR | No | No | Golden first name selected via source priority + recency survivorship. |
| `golden_last_name` | VARCHAR | No | No | Golden last name selected via survivorship. |
| `golden_email` | VARCHAR | Yes | No | Highest-reliability validated email address. |
| `golden_phone` | VARCHAR | Yes | No | Highest-reliability standardized telephone number. |
| `primary_address` | VARCHAR | Yes | No | Normalized primary street address. |
| `primary_city` | VARCHAR | Yes | No | Primary city. |
| `primary_state` | VARCHAR | Yes | No | Primary state/province. |
| `primary_postal_code` | VARCHAR | Yes | No | Primary postal/ZIP code. |
| `primary_country` | VARCHAR | Yes | No | Primary country. |
| `date_of_birth` | VARCHAR | Yes | No | Validated date of birth. |
| `tax_id` | VARCHAR | Yes | No | Masked national tax identifier. |
| `source_record_count` | INTEGER | No | No | Number of distinct source system customer records merged into this golden entity. |
| `confidence_score` | DOUBLE | No | No | Match rule confidence score (0.00 to 1.00). |
| `primary_source_system` | VARCHAR | No | No | Dominant source system providing the primary identity attributes. |
| `created_at` | VARCHAR | No | No | Earliest creation timestamp among cluster members. |
| `updated_at` | VARCHAR | No | No | Latest update timestamp among cluster members. |
| `run_id` | VARCHAR | No | No | Pipeline execution run ID. |

---

### 2.2 `bridge_customer_source_map` (Identity Lineage Bridge)
- **Business Description**: Preserves complete source-to-target traceability, documenting which rule matched each source record.
- **Grain**: One record per source customer record mapped to a unified customer.
- **Primary Key**: `mapping_id`
- **Foreign Key**: `unified_customer_id` -> `dim_unified_customer.unified_customer_id`

| Column Name | Data Type | Nullable? | Uniqueness | Description / Business Rules |
| :--- | :--- | :---: | :---: | :--- |
| `mapping_id` | VARCHAR | No | Yes (PK) | Unique mapping record hash `MAP_<md5_hash>`. |
| `unified_customer_id` | VARCHAR | No | No (FK) | Reference to master golden customer. |
| `source_system` | VARCHAR | No | No | Source system name. |
| `source_customer_id` | VARCHAR | No | No | Upstream customer ID. |
| `match_rule_applied` | VARCHAR | No | No | Documented rule: `RULE_EXACT_TAX_ID`, `RULE_EXACT_EMAIL`, `RULE_EXACT_PHONE_AND_LAST_NAME`, `RULE_EXACT_NAME_AND_ADDRESS`, `SINGLETON`. |
| `match_confidence` | DOUBLE | No | No | Rule confidence score (`1.00`, `0.98`, `0.92`, `0.88`, `1.00`). |
| `is_uncertain` | BOOLEAN | No | No | Boolean flag indicating whether the match was flagged for review. |
| `source_created_at` | VARCHAR | Yes | No | Original source record creation timestamp. |
| `source_updated_at` | VARCHAR | Yes | No | Original source record update timestamp. |
| `ingested_at` | VARCHAR | No | No | Timestamp when record was ingested into target layer. |
| `run_id` | VARCHAR | No | No | Pipeline execution run ID. |

---

### 2.3 `dim_account_unified` (Unified Account Dimension)
- **Business Description**: Account dimension enriched with parent `unified_customer_id`.
- **Grain**: One record per account.
- **Primary Key**: `account_id`
- **Foreign Key**: `unified_customer_id` -> `dim_unified_customer.unified_customer_id`

---

### 2.4 `fct_order_unified` (Unified Order Fact)
- **Business Description**: Order transaction fact table linked to `unified_customer_id`.
- **Grain**: One record per order transaction.
- **Primary Key**: `order_id`
- **Foreign Key**: `unified_customer_id` -> `dim_unified_customer.unified_customer_id`

---

### 2.5 `fct_interaction_unified` (Unified Interaction Fact)
- **Business Description**: Customer touchpoint fact table linked to `unified_customer_id`.
- **Grain**: One record per support interaction.
- **Primary Key**: `interaction_id`
- **Foreign Key**: `unified_customer_id` -> `dim_unified_customer.unified_customer_id`

---

### 2.6 `fact_customer_360_summary` (Customer 360 Feature Store & Aggregates)
- **Business Description**: Aggregated behavioral, financial, and engagement metrics computed per golden customer.
- **Grain**: Exactly one record per `unified_customer_id`.
- **Primary Key**: `unified_customer_id`

| Column Name | Data Type | Nullable? | Description / Business Rules |
| :--- | :--- | :---: | :--- |
| `unified_customer_id` | VARCHAR | No (PK) | Foreign key to golden customer. |
| `total_accounts` | INTEGER | No | Count of all accounts owned across all source systems. |
| `active_accounts` | INTEGER | No | Count of currently active accounts (`status = 'ACTIVE'`). |
| `lifetime_order_count` | INTEGER | No | Total count of all placed orders. |
| `completed_order_count` | INTEGER | No | Total count of completed/delivered orders. |
| `lifetime_spend_usd` | DOUBLE | No | Sum of `total_amount` for completed orders. Financial reconciliation target. |
| `average_order_value_usd`| DOUBLE | No | `lifetime_spend_usd / completed_order_count`. |
| `first_order_timestamp` | VARCHAR | Yes | Earliest transaction timestamp. |
| `last_order_timestamp` | VARCHAR | Yes | Most recent transaction timestamp. |
| `total_interactions` | INTEGER | No | Total omnichannel touchpoints across chat, phone, email, and portal. |
| `open_tickets_count` | INTEGER | No | Count of tickets with status `OPEN`, `ESCALATED`, or `PENDING_USER`. |
| `avg_sentiment_score` | DOUBLE | No | Mean sentiment score across all customer touchpoints. |
| `last_interaction_timestamp` | VARCHAR | Yes | Most recent support interaction timestamp. |
| `customer_segment` | VARCHAR | No | `VIP` (spend >= $1000 & orders >= 2), `HIGH_VALUE` (spend >= $500), `AT_RISK` (tickets >= 2 or sentiment < -0.2), `REGULAR`, `PROSPECT`. |
| `last_computed_at` | VARCHAR | No | UTC timestamp of feature calculation. |
| `run_id` | VARCHAR | No | Pipeline execution run ID. |

---

## 3. Quarantine and Operational Tables

### 3.1 `quarantine_rejected_records` (Dead-Letter Store)
- **Business Description**: Holds all records rejected during validation with full raw payload and diagnostic error reasons.
- **Grain**: One record per rejected row per validation failure.
- **Primary Key**: `quarantine_id`

| Column Name | Data Type | Nullable? | Description |
| :--- | :--- | :---: | :--- |
| `quarantine_id` | VARCHAR | No (PK) | Unique quarantine record identifier `QRN_<uuid>`. |
| `run_id` | VARCHAR | No | Pipeline run ID that detected the failure. |
| `source_table` | VARCHAR | No | Entity table name (`customers`, `accounts`, `orders`, `interactions`). |
| `source_record_id` | VARCHAR | Yes | Upstream record identifier. |
| `source_system` | VARCHAR | Yes | Upstream system name. |
| `rejection_category` | VARCHAR | No | `MISSING_REQUIRED_FIELD`, `MALFORMED_INPUT`, `OUT_OF_BOUNDS_VALUE`, `REFERENTIAL_INTEGRITY_VIOLATION`, `DUPLICATE_KEY_CONFLICT`. |
| `rejection_reason` | VARCHAR | No | Human-readable root-cause diagnostic message. |
| `raw_record_json` | TEXT | No | Full unedited raw record serialized in JSON for auditing and backfill re-processing. |
| `quarantined_at` | VARCHAR | No | UTC timestamp of quarantine action. |

---

### 3.2 `uncertain_matches_review` (Probabilistic / Ambiguous Match Queue)
- **Business Description**: Holds candidate pairs meeting ambiguous similarity criteria that require human review and are prevented from merging.
- **Grain**: One record per candidate pair flagged for manual review.
- **Primary Key**: `review_id`

| Column Name | Data Type | Nullable? | Description |
| :--- | :--- | :---: | :--- |
| `review_id` | VARCHAR | No (PK) | Unique review identifier `REV_<uuid>`. |
| `run_id` | VARCHAR | No | Pipeline run ID that flagged the match. |
| `entity_1_source` / `entity_1_id` | VARCHAR | No | Source system and record ID for first candidate. |
| `entity_1_name` / `email` / `phone` | VARCHAR | Yes | Profile attributes for candidate 1. |
| `entity_2_source` / `entity_2_id` | VARCHAR | No | Source system and record ID for second candidate. |
| `entity_2_name` / `email` / `phone` | VARCHAR | Yes | Profile attributes for candidate 2. |
| `match_heuristic` | VARCHAR | No | Reason: `UNCERTAIN_SHARED_PHONE_DIFFERENT_NAME`, `UNCERTAIN_SAME_ADDRESS_DIFFERENT_FIRST_NAME`, `UNCERTAIN_HIGH_NAME_SIMILARITY_SAME_ZIP`. |
| `similarity_score` | DOUBLE | No | Computed similarity score (e.g. 0.60 to 0.87). |
| `review_status` | VARCHAR | No | `PENDING_REVIEW`, `APPROVED`, `REJECTED`. |
| `flagged_at` | VARCHAR | No | UTC timestamp when flagged. |

---

### 3.3 `pipeline_run_audit` (Operational Lineage & Run Ledger)
- **Business Description**: System ledger recording execution timings, row counts, and health status for each pipeline run.
- **Grain**: One record per pipeline execution run.
- **Primary Key**: `run_id`

| Column Name | Data Type | Nullable? | Description |
| :--- | :--- | :---: | :--- |
| `run_id` | VARCHAR | No (PK) | Pipeline run identifier (e.g. `RUN_20261112_032352_7DA65B`). |
| `batch_id` | VARCHAR | Yes | Logical batch identifier. |
| `status` | VARCHAR | No | Final run status (`STARTED`, `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`). |
| `start_time` | VARCHAR | No | UTC start timestamp. |
| `end_time` | VARCHAR | Yes | UTC completion timestamp. |
| `duration_seconds` | DOUBLE | Yes | Total pipeline runtime in seconds. |
| `total_input_rows` | INTEGER | No | Total raw records ingested across all tables. |
| `total_valid_rows` | INTEGER | No | Total records passing data quality checks. |
| `total_quarantined_rows` | INTEGER | No | Total rejected records routed to dead-letter store. |
| `total_golden_customers` | INTEGER | No | Count of master golden customer records created. |
| `total_uncertain_matches` | INTEGER | No | Count of ambiguous candidate pairs sent for review. |
| `input_counts_json` | TEXT | Yes | Breakdown of input rows per entity in JSON format. |
| `valid_counts_json` | TEXT | Yes | Breakdown of valid rows per entity in JSON format. |
| `quarantined_counts_json` | TEXT | Yes | Breakdown of quarantined rows per entity in JSON format. |
| `target_counts_json` | TEXT | Yes | Breakdown of target rows published in JSON format. |
| `error_message` | TEXT | Yes | Exception message if pipeline encountered a fatal error. |
