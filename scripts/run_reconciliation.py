#!/usr/bin/env python3
"""
CLI script to execute reconciliation checks against published Customer 360 tables.
"""

import argparse
import sys
from pathlib import Path
import duckdb

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.reconciliation import ReconciliationEngine


def main():
    parser = argparse.ArgumentParser(description="Customer 360 Reconciliation CLI")
    parser.add_argument(
        "--duckdb-path",
        type=str,
        default="data/output/customer_360.duckdb",
        help="Path to DuckDB database",
    )
    parser.add_argument(
        "--labels-file",
        type=str,
        default="data/expected_labels/expected_golden_customers.csv",
        help="Path to ground truth labels file",
    )
    args = parser.parse_args()

    db_path = Path(args.duckdb_path)
    if not db_path.exists():
        print(f"Error: Database {db_path} does not exist. Run pipeline first.")
        sys.exit(1)

    conn = duckdb.connect(str(db_path))
    try:
        # Fetch latest run audit counts if available
        audit_res = conn.execute("""
            SELECT run_id, input_counts_json, valid_counts_json, quarantined_counts_json 
            FROM pipeline_run_audit 
            ORDER BY start_time DESC LIMIT 1
        """).fetchone()

        if audit_res:
            import json
            run_id = audit_res[0]
            in_c = json.loads(audit_res[1])
            val_c = json.loads(audit_res[2])
            q_c = json.loads(audit_res[3])
        else:
            run_id = "MANUAL_INSPECTION"
            in_c, val_c, q_c = {}, {}, {}

        labels_path = Path(args.labels_file)
        engine = ReconciliationEngine(duckdb_conn=conn, run_id=run_id)
        report = engine.run_all_checks(
            input_counts=in_c,
            valid_counts=val_c,
            quarantine_counts=q_c,
            expected_labels_file=labels_path if labels_path.exists() else None,
        )

        print("\n" + report.to_markdown() + "\n")
        if report.overall_status != "PASSED":
            sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
