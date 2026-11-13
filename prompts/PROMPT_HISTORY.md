# Prompt History & AI Interaction Log

As required by **YottaFlex AI Candidate Project Submission Guidelines (Item 03: USE LLMs TRANSPARENTLY)** and **FAQ 6**, this document provides a comprehensive, chronological record of all prompts submitted to AI assistance tools during the design, implementation, debugging, and benchmarking of this project.

---

## AI Tools Used
- **Primary Tool**: Gemini 3.8 Flash (High) / Antigravity Agentic Assistant
- **Environment**: Local Windows 11 x64, Python 3.13.5
- **Disclosure Statement**: A companion technical disclosure explaining where AI accelerated development, where it was relied upon, and what was personally reviewed, rewritten, and validated is provided in [AI_DISCLOSURE.md](../docs/AI_DISCLOSURE.md).

---

## Chronological Prompt Log

### Phase 1: Problem Decomposition, Architecture, & Requirements Analysis
- **Prompt ID**: `PROMPT-01`
- **Timestamp**: `2026-11-12T08:35:56Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Analyze business problem, break down requirements across customer 360, deterministic entity resolution, lineage preservation, dead-letter quarantine, idempotency, testing, and reconciliation.
- **Submitted Prompt**:
  ```text
  Problem statement
  Read it carefully. Your build should cover every point below.

  Business Context / Problem:
  Combine customer, account, order, and interaction datasets into a unified customer view. Resolve duplicates with documented deterministic rules, preserve source lineage, and flag uncertain matches.

  Objective and Scope:
  Deliver a working Data Engineering solution within 72 hours for: Combine customer, account, order, and interaction datasets into a unified customer view. Resolve duplicates with documented deterministic rules, preserve source lineage, and flag uncertain matches. The solution should be runnable locally or in a clearly documented cloud environment, expose failures and data-quality issues, and produce measurable outputs. Target level: 0–3 years of experience. Prioritize correctness, clear design, maintainability, and evidence of testing over unnecessary complexity.

  [Full 10-step instructions, edge cases, suggested volume 100k+, acceptance criteria, and 72-hour deliverables]
  ```
- **Outcome**: Decomposed architecture into 9 decoupled modules: Ingestion, Validation & Quarantine, Entity Resolution, Feature Store Transformation, ACID Target Storage, Observability, Reconciliation, Benchmarking, and CLI orchestrators.

---

### Phase 2: Schema Contracts & Scalable Synthetic Data Generation
- **Prompt ID**: `PROMPT-02`
- **Timestamp**: `2026-11-12T08:38:30Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Define source schemas, conformed target schemas, dead-letter quarantine schemas, and implement a scalable synthetic data generator with a fixed random seed.
- **Submitted Prompt**:
  ```text
  Design source and target schemas for customer, account, order, and interaction datasets.
  Implement a reproducible dataset generator supporting both a small starter sample (~400 records) and a scalable benchmark dataset (100k+ records) using a fixed random seed. Ensure the generator includes deliberate anomalies:
  - Exact Tax ID match across CRM and Web Store
  - Exact Email match with case/whitespace variations
  - Exact Phone + Last Name match with formatted telephone numbers
  - Exact Name + Address match with standard street abbreviations
  - Ambiguous matches to flag for human review: shared phone with different last names, and same household with different first names
  - Malformed inputs: bad emails, invalid timestamps, out-of-bounds sentiment scores
  - Orphan foreign keys: accounts without customers, orders without accounts, interactions without customers
  - In-batch duplicate keys (both identical and conflicting duplicates)
  Keep expected-answer ground-truth labels in a separate file (expected_golden_customers.csv).
  ```
- **Outcome**: Created `src/schemas.py`, `docs/DATA_DICTIONARY.md`, `src/generator.py`, and `scripts/generate_data.py`.

---

### Phase 3: Core Pipeline Implementation (Validation, Entity Resolution, Storage)
- **Prompt ID**: `PROMPT-03`
- **Timestamp**: `2026-11-12T08:41:00Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Implement topological data quality validation, candidate blocking, deterministic multi-tier matching rules, disjoint-set graph clustering, and DuckDB ACID target publishing.
- **Submitted Prompt**:
  ```text
  Implement the core data engineering pipeline:
  1. Ingestion: Support CSV, JSON, Parquet; inject lineage metadata (_source_file, _ingested_at, _run_id); handle 0-byte empty batches gracefully.
  2. Data Validation: Topological checks on customers, accounts, orders, interactions. Route malformed rows and orphan foreign keys to quarantine_rejected_records with raw JSON payloads and diagnostic reasons.
  3. Deterministic Entity Resolution:
     - Field normalizers for names, emails, phones, tax IDs, and street addresses.
     - Hash-partitioned candidate blocking on (tax_id, email, phone, zip) to achieve O(N) runtime instead of O(N^2).
     - Deterministic rule tiers: Tier 1 (Tax ID, 1.0), Tier 2 (Email, 0.98), Tier 3 (Phone + Last Name, 0.92), Tier 4 (Name + Address, 0.88).
     - Flag uncertain matches (shared phone, same household) into uncertain_matches_review with PENDING_REVIEW status and DO NOT auto-merge them.
     - Disjoint-set graph clustering for connected components.
     - Deterministic golden ID generation from canonical cluster seed: UC_<sha256>.
     - Survivorship: source priority (CRM > Billing > Web > Support) + recency + non-null coalescing.
  4. Transformation: Customer 360 Feature Store (lifetime spend, order counts, sentiment score, customer segmentation).
  5. Storage: ACID DuckDB tables, Columnar Parquet exports, and operational CSV files.
  6. Observability: Structured logging, execution timings, and pipeline_run_audit ledger.
  ```
- **Outcome**: Created `src/ingestion.py`, `src/validation.py`, `src/entity_resolution.py`, `src/transformation.py`, `src/storage.py`, `src/observability.py`, and `src/pipeline.py`.

---

### Phase 4: Automated Testing & Edge Case Verification
- **Prompt ID**: `PROMPT-04`
- **Timestamp**: `2026-11-12T08:46:00Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Author comprehensive automated tests for all acceptance criteria and required negative scenarios.
- **Submitted Prompt**:
  ```text
  Create automated pytest test suites covering:
  - Happy path end-to-end execution
  - Empty batch / zero-byte input files
  - Malformed records (invalid emails, bad timestamps, out-of-range sentiment)
  - Null and missing mandatory fields
  - In-batch duplicates (both identical skip and conflicting key quarantine)
  - Referential integrity violations (orphan accounts, orders, interactions)
  - Deterministic entity resolution tiers and graph transitivity
  - Domain edge case 1: Shared phone with different names (roommates) flagged uncertain and NOT merged
  - Domain edge case 2: Same household with different first names (family) flagged uncertain and NOT merged
  - Domain edge case 3: Late-arriving out-of-order data preserving newer golden attributes
  - Domain edge case 4: Multi-source financial aggregation and refund adjustments
  - Idempotency: Running the pipeline twice yields identical row counts and identical golden customer IDs.
  ```
- **Outcome**: Created 14 pytest unit and integration tests across 9 test modules in `tests/`.

---

### Phase 5: Debugging, Defect Diagnosis, & Performance Optimization (Human Validation)
- **Prompt ID**: `PROMPT-05`
- **Timestamp**: `2026-11-12T08:49:30Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Debug Windows file handle permission errors in test cleanup, fix rule precedence collision, eliminate DuckDB connection resource locks during reconciliation, and vectorize ground-truth assertions.
- **Submitted Prompt**:
  ```text
  Analyze the pytest execution logs:
  1. Fix Windows PermissionError [WinError 32] where tempfile.TemporaryDirectory cleanup fails because logging.FileHandler holds an open lock on the log file.
  2. Fix AssertionError in test_matching_tiers_and_clustering where Rule 4 (Name + Address) overwrote Rule 1 (Tax ID) in match_lineage because lower-confidence rules were not checking existing higher-confidence matches.
  3. Fix _duckdb.ResourceInUseException where calling conn.register() inside reconciliation queries caused connection contention in DuckDB 2.0.0.
  4. Vectorize ground-truth reconciliation assertions to replace 25,000 iterative SQL queries with pure in-memory vectorized lookups.
  ```
- **Outcome**: Added `observer.close()` to release file handles; implemented `record_match()` with strict confidence protection; replaced iterative SQL lookups with in-memory Pandas vectorized merges; all 14 tests passed with 100% success rate.

---

### Phase 6: Packaging, Git Versioning, & Submission Artifacts
- **Prompt ID**: `PROMPT-06`
- **Timestamp**: `2026-11-12T09:09:35Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Package the project as a standalone ZIP archive, initialize clean Git history, and prepare submission artifacts.
- **Submitted Prompt**:
  ```text
  Get me this project in a file from that I can access this and I can share that file to my git.
  ```
- **Outcome**: Initialized Git repository on `main` branch with clean `.gitignore`, created standalone `customer_360_pipeline.zip` (220 KB), and generated full quickstart commands.

---

### Phase 7: Compliance with YottaFlex AI Guidelines & FAQ
- **Prompt ID**: `PROMPT-07`
- **Timestamp**: `2026-11-12T10:26:03Z`
- **Tool**: Gemini 3.8 Flash
- **Intent**: Align the repository strictly with the two YottaFlex AI PDF documents: Candidate Project Submission Guidelines (01 Make It Run, 02 Show Your Work, 03 Use LLMs Transparently, 04 Make Your Reasoning Visible) and FAQ.
- **Submitted Prompt**:
  ```text
  Make this project according to this PDFs:
  - YottaFlex AI Candidate Project Submission Guidelines (Make it run, Show your work, Use LLMs transparently, Make your reasoning visible)
  - Candidate Project FAQ (72 hours, public github, transparent AI use, prompt history required in clearly identifiable directory, explain the why, walk us through your solution)
  ```
- **Outcome**: Created `prompts/PROMPT_HISTORY.md`, `prompts/prompts.json`, `docs/AI_DISCLOSURE.md`, `docs/WALKTHROUGH_GUIDE.md`, `SUBMISSION_CHECKLIST.md`, and structured Git commit history.
