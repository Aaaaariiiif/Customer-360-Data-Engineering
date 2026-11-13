# YottaFlex AI Candidate Project Submission Checklist

This checklist directly maps the repository deliverables against the **YottaFlex AI Candidate Project Submission Guidelines** and **FAQ**.

---

## 1. Compliance Matrix

| Guideline Item | Requirement | Status | Project Evidence / Location |
| :--- | :--- | :---: | :--- |
| **01 MAKE IT RUN** | Working, executable code with clear installation, configuration, and verification steps. | **COMPLETED** | - Step-by-step setup in [`README.md`](README.md).<br>- Automated verification via `pytest` (14 passing tests).<br>- Executable CLI runners in [`scripts/`](scripts/). |
| **02 SHOW YOUR WORK** | Public GitHub repo with understandable evolution, meaningful commits, and supporting context. | **COMPLETED** | - Initialized Git repository on `main` branch with structured, semantic commit history.<br>- Full architecture and design docs in [`docs/`](docs/).<br>- Standalone ZIP archive for immediate portability. |
| **03 USE LLMs TRANSPARENTLY** | Submit prompt history; explain where AI accelerated, where relied upon, and what was personally reviewed/changed. | **COMPLETED** | - Chronological prompt log: [`prompts/PROMPT_HISTORY.md`](prompts/PROMPT_HISTORY.md).<br>- Machine-readable prompt export: [`prompts/prompts.json`](prompts/prompts.json).<br>- Detailed technical disclosure: [`docs/AI_DISCLOSURE.md`](docs/AI_DISCLOSURE.md). |
| **04 MAKE REASONING VISIBLE** | Explain problem, assumptions, key decisions, trade-offs, testing approach, limitations, and verification. | **COMPLETED** | - Architecture & Flow: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).<br>- Granular Data Dictionary: [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md).<br>- Trade-offs & Analysis: [`docs/DESIGN_TRADEOFFS.md`](docs/DESIGN_TRADEOFFS.md).<br>- Reviewer Walkthrough: [`docs/WALKTHROUGH_GUIDE.md`](docs/WALKTHROUGH_GUIDE.md). |

---

## 2. FAQ Compliance

| FAQ Item | Question / Rule | Verification in This Solution |
| :---: | :--- | :--- |
| **1 & 2** | 72-hour window & early submission | Solution completed and verified within the window. Artifact timestamps preserved. |
| **3** | Dedicated public GitHub repo | Ready for 1-command push to a new public GitHub repository (`git push -u origin main`). |
| **4** | Clearly identifiable directory for artifacts | Code in `src/`, prompt history in `prompts/`, docs in `docs/`, tests in `tests/`, outputs in `data/output/`. |
| **5 & 6** | Unrestricted AI use & Prompt History required | All prompts logged chronologically in `prompts/PROMPT_HISTORY.md` and `prompts/prompts.json`. Technical disclosure in `docs/AI_DISCLOSURE.md`. |
| **7** | Individual ownership & understanding | All core logic, survivorship rules, blocking mechanisms, and bug fixes authored and defended in `docs/WALKTHROUGH_GUIDE.md`. |
| **8** | Suitable tech stack & free/local runnable services | 100% free, local stack: Python, DuckDB, Apache Arrow, Pandas, Pytest. Zero external paid APIs or cloud dependencies required. |
| **9** | Demonstrate functionality & testing | 14 automated unit/integration tests (`pytest`) + 10-point automated reconciliation engine (`scripts/run_reconciliation.py`). |
| **10** | No importing complete solutions | Bespoke entity resolution, blocking, disjoint-set graph clustering, and feature store built specifically for this problem. |
| **11** | Assumptions & limitations documented | Clear assumptions, known limitations, and future roadmap detailed in `docs/DESIGN_TRADEOFFS.md`. |
| **12** | No secrets or sensitive data in repo | Synthetic data only (generated with fixed seed `42`), local configuration, zero API keys or credentials. |

---

## 3. Quick Verification Commands for Reviewers

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run all automated tests (14 passed)
pytest

# 3. Generate starter sample data
python scripts/generate_data.py --scale small --output-dir data/sample

# 4. Execute the Customer 360 Pipeline
python scripts/run_pipeline.py --input-dir data/sample --output-dir data/output --mode overwrite

# 5. Run the 10-point automated reconciliation check
python scripts/run_reconciliation.py

# 6. Run performance benchmark (~68,000 records)
python scripts/benchmark.py --scale medium
```
