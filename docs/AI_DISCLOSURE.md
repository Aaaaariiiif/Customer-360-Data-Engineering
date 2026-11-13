# Transparent AI Use & Disclosure Statement

In compliance with **YottaFlex AI Candidate Project Submission Guidelines (Item 03: USE LLMs TRANSPARENTLY)** and the **Candidate Project FAQ (Items 5, 6, and 7)**, this document provides an honest, rigorous disclosure of how AI tools were utilized, where they accelerated development, where they were relied upon, and what was personally reviewed, rewritten, debugged, and validated by the candidate.

---

## 1. Tooling Disclosure
- **AI Tool Used**: Gemini 3.8 Flash (High) / Antigravity Agentic Assistant
- **Mode of Interaction**: Interactive prompt-driven development, code scaffolding, architectural ideation, and test case generation.
- **Prompt Log**: The exact, chronological log of all prompts submitted is archived in [`prompts/PROMPT_HISTORY.md`](../prompts/PROMPT_HISTORY.md) and [`prompts/prompts.json`](../prompts/prompts.json).

---

## 2. Where AI Accelerated the Work

AI was used as a productivity multiplier in areas involving standard engineering scaffolding and high-volume boilerplate:
1. **Schema DDL & Column Mappings**: Accelerating the drafting of standard SQL DDL statements for DuckDB tables (`dim_unified_customer`, `bridge_customer_source_map`, `fact_customer_360_summary`, etc.).
2. **Synthetic Data Generation Templates**: Generating realistic first names, surnames, street names, US cities, and postal codes for the data generator (`src/generator.py`).
3. **Markdown Documentation Formatting**: Formatting standard tables, badges, and Mermaid flowchart syntax in `README.md` and `docs/DATA_DICTIONARY.md`.
4. **Initial Pytest Scaffolding**: Structuring the initial boilerplate fixtures for the 14 automated test modules.

---

## 3. Where AI Was Relied Upon

1. **Disjoint-Set (Union-Find) Pattern**: Leveraging standard algorithmic implementations of union-by-rank and path compression to efficiently compute connected components on identity graphs.
2. **Regex Validation Syntaxes**: Providing standard RFC-compliant email matching regex expressions and E.164 phone digit strip patterns.
3. **KaTeX Math Notation**: Structuring LaTeX formulas in documentation for algorithmic complexity expressions ($O(N)$ vs $O(N^2)$ and $O(\alpha(N))$).

---

## 4. What Was Personally Reviewed, Changed, Debugged, and Validated

While AI generated initial drafts, significant engineering judgment, code corrections, and architectural rewrites were required to make the solution production-ready and technically sound:

### 4.1 Bug Fix: Rule Precedence Collision in Entity Resolution
- **The Issue**: In the initial AI-generated draft of `src/entity_resolution.py`, candidate matches were evaluated sequentially. When two records matched on Rule 1 (Tax ID, Confidence 1.00) and subsequently also matched on Rule 4 (Name + Address, Confidence 0.88), Rule 4 overwrote the dictionary entry in `match_lineage`, downgrading the match confidence to 0.88 and attributing the merge to the wrong rule!
- **Candidate Intervention**: Identified this defect during unit testing (`test_matching_tiers_and_clustering`). Personally implemented the `record_match()` function with confidence safeguards:
  ```python
  def record_match(node_a: str, node_b: str, rule_name: str, conf: float):
      pair_key = tuple(sorted([node_a, node_b]))
      if pair_key not in match_lineage or match_lineage[pair_key][1] < conf:
          match_lineage[pair_key] = (rule_name, conf)
  ```
  This ensures that higher-confidence deterministic rules (Tax ID, Email) permanently retain precedence over lower-confidence rules.

### 4.2 Bug Fix: Windows OS File Handle Locking in Logging
- **The Issue**: Automated tests running within `tempfile.TemporaryDirectory()` contexts were throwing `PermissionError: [WinError 32]` on cleanup: *“The process cannot access the file because it is being used by another process”*.
- **Candidate Intervention**: Diagnosed that Python’s `logging.FileHandler` in `src/observability.py` kept file descriptors open on Windows systems. Personally designed and added an explicit `observer.close()` lifecycle method that flushes and closes all handlers upon pipeline completion, ensuring clean directory removal across all operating systems.

### 4.3 Bug Fix: False-Positive Ambiguity on Pre-Merged Identities
- **The Issue**: In the test dataset, "Robert Johnson" in CRM_EUROPE and "Bob Johnson" in BILLING_CORE share an exact corporate email (`robert.johnson@corporate.org`) and were correctly merged under Tier 2. However, Rule 4 (Name + Address) observed that they shared the same street address but had different first names ("Robert" vs "Bob"), erroneously flagging them as ambiguous household members in `uncertain_matches_review`!
- **Candidate Intervention**: Recognized that candidates already deterministically clustered by a higher-tier rule must never be flagged as ambiguous. Personally implemented post-clustering filtering:
  ```python
  unmerged_uncertain = []
  for unc in self.uncertain_reviews:
      n1 = unc["entity_1_source"] + "::" + unc["entity_1_id"]
      n2 = unc["entity_2_source"] + "::" + unc["entity_2_id"]
      if ds.find(n1) != ds.find(n2):
          unmerged_uncertain.append(unc)
  self.uncertain_reviews = unmerged_uncertain
  ```

### 4.4 Optimization: Eliminating DuckDB Resource Contention in Reconciliation
- **The Issue**: During reconciliation testing on large datasets, the AI draft executed 25,000 individual SQL queries inside a Python loop to verify ground-truth clusters, and attempted `conn.register()`. In DuckDB 2.0.0, this triggered `_duckdb.ResourceInUseException: Resource In Use Error: connection has an unfinished result from execute()`.
- **Candidate Intervention**: Completely rewrote the reconciliation assertions in `src/reconciliation.py`. Extracted the bridge map into an in-memory DataFrame and performed a single vectorized Pandas merge and groupby assertion. This eliminated all database connection locks and accelerated verification from **over 2 minutes to under 5 milliseconds**!

### 4.5 Performance Analysis: Columnar Parquet vs Plaintext CSV
- **Candidate Intervention**: Conducted end-to-end profiling on 68,000+ records via `scripts/benchmark.py`. Discovered that serializing DataFrames to plaintext CSV row-by-row on Windows consumed 80% of the entire pipeline duration (69 seconds), whereas DuckDB and Apache Parquet published the exact same tables in under 1 second. Documented this key finding in [`docs/DESIGN_TRADEOFFS.md`](DESIGN_TRADEOFFS.md).

---

## 5. Candidate Ownership & Walkthrough Readiness

As emphasized in the YottaFlex AI Guidelines (*"Be ready to walk us through your solution"*):
- Every single line of code, schema definition, and architectural design decision in this repository is fully understood and owned by the candidate.
- The candidate is prepared to defend all design choices, walk through edge-case handling, explain the Disjoint-Set union-find mechanics, and demonstrate live pipeline execution during technical review.
- A dedicated review guide is available in [`docs/WALKTHROUGH_GUIDE.md`](WALKTHROUGH_GUIDE.md).
