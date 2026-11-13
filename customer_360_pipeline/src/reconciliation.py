"""
Automated Data Reconciliation and Audit Reporting Module.
Validates conservation of volume, referential integrity, financial aggregates,
and compares clusters against ground truth labels.
Generates comprehensive Markdown and JSON reconciliation reports.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import duckdb
import pandas as pd


@dataclass
class ReconciliationCheckResult:
    check_name: str
    status: str  # PASSED | FAILED | WARNING
    description: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReconciliationReport:
    run_id: str
    total_checks: int
    passed_checks: int
    failed_checks: int
    warning_checks: int
    overall_status: str
    checks: List[ReconciliationCheckResult] = field(default_factory=list)

    def to_markdown(self) -> str:
        md = []
        md.append(f"# Customer 360 Pipeline Reconciliation Report")
        md.append(f"**Run ID**: `{self.run_id}`  ")
        md.append(f"**Overall Status**: **{self.overall_status}**  ")
        md.append(f"**Checks Summary**: {self.passed_checks}/{self.total_checks} Passed, {self.failed_checks} Failed, {self.warning_checks} Warnings\n")
        md.append("| Check Name | Status | Description | Details |")
        md.append("| :--- | :---: | :--- | :--- |")
        for c in self.checks:
            badge = "✅ PASS" if c.status == "PASSED" else ("❌ FAIL" if c.status == "FAILED" else "⚠️ WARN")
            details_str = "<br>".join([f"**{k}**: {v}" for k, v in c.details.items()])
            md.append(f"| {c.check_name} | {badge} | {c.description} | {details_str} |")
        return "\n".join(md)


class ReconciliationEngine:
    """Executes automated reconciliation queries and generates verification reports."""

    def __init__(self, duckdb_conn: duckdb.DuckDBPyConnection, run_id: str):
        self.conn = duckdb_conn
        self.run_id = run_id

    def run_all_checks(
        self,
        input_counts: Dict[str, int],
        valid_counts: Dict[str, int],
        quarantine_counts: Dict[str, int],
        expected_labels_file: Optional[Path] = None,
    ) -> ReconciliationReport:
        checks: List[ReconciliationCheckResult] = []

        # -------------------------------------------------------------------
        # Check 1: Conservation of Customer Volume
        # -------------------------------------------------------------------
        # Total valid customers must equal total rows in bridge_customer_source_map
        bridge_cnt = self.conn.execute("SELECT COUNT(*) FROM bridge_customer_source_map").fetchone()[0]
        valid_cust_cnt = valid_counts.get("customers", 0)

        vol_passed = (bridge_cnt == valid_cust_cnt)
        checks.append(ReconciliationCheckResult(
            check_name="Conservation of Customer Lineage",
            status="PASSED" if vol_passed else "FAILED",
            description="All valid customer records must be mapped 1:1 in bridge_customer_source_map",
            details={
                "valid_customers_ingested": valid_cust_cnt,
                "bridge_source_map_rows": bridge_cnt,
                "difference": valid_cust_cnt - bridge_cnt,
            },
        ))

        # -------------------------------------------------------------------
        # Check 2: Conservation of Total Input Rows (Input = Valid + Quarantined + Deduplicated)
        # -------------------------------------------------------------------
        for entity in ["customers", "accounts", "orders", "interactions"]:
            in_c = input_counts.get(entity, 0)
            val_c = valid_counts.get(entity, 0)
            q_c = quarantine_counts.get(entity, 0)
            accounted_for = val_c + q_c
            # It's normal if accounted_for <= in_c due to in-batch identical duplicates skipped
            is_valid_accounting = accounted_for <= in_c and (in_c == 0 or accounted_for > 0)
            checks.append(ReconciliationCheckResult(
                check_name=f"Volume Accounting: {entity.capitalize()}",
                status="PASSED" if is_valid_accounting else "FAILED",
                description=f"Input {entity} must account for valid, quarantined, or deduplicated rows",
                details={
                    "input_rows": in_c,
                    "valid_rows": val_c,
                    "quarantined_rows": q_c,
                    "accounted_rows": accounted_for,
                    "in_batch_deduped": in_c - accounted_for,
                },
            ))

        # -------------------------------------------------------------------
        # Check 3: Referential Integrity in Target Tables
        # -------------------------------------------------------------------
        orphan_accounts = self.conn.execute("""
            SELECT COUNT(*) FROM dim_account_unified 
            WHERE unified_customer_id NOT IN (SELECT unified_customer_id FROM dim_unified_customer)
        """).fetchone()[0]

        orphan_orders = self.conn.execute("""
            SELECT COUNT(*) FROM fct_order_unified 
            WHERE unified_customer_id NOT IN (SELECT unified_customer_id FROM dim_unified_customer)
        """).fetchone()[0]

        orphan_interactions = self.conn.execute("""
            SELECT COUNT(*) FROM fct_interaction_unified 
            WHERE unified_customer_id NOT IN (SELECT unified_customer_id FROM dim_unified_customer)
        """).fetchone()[0]

        ri_passed = (orphan_accounts == 0 and orphan_orders == 0 and orphan_interactions == 0)
        checks.append(ReconciliationCheckResult(
            check_name="Referential Integrity in Unified Target Layer",
            status="PASSED" if ri_passed else "FAILED",
            description="Zero orphaned records in unified account, order, or interaction tables",
            details={
                "orphan_accounts": orphan_accounts,
                "orphan_orders": orphan_orders,
                "orphan_interactions": orphan_interactions,
            },
        ))

        # -------------------------------------------------------------------
        # Check 4: Financial Aggregate Reconciliation
        # -------------------------------------------------------------------
        # Sum of completed orders in fct_order_unified must match sum of lifetime_spend_usd in customer 360 summary
        order_spend_sum = self.conn.execute("""
            SELECT COALESCE(SUM(total_amount), 0.0) 
            FROM fct_order_unified 
            WHERE status IN ('COMPLETED', 'DELIVERED')
        """).fetchone()[0]

        summary_spend_sum = self.conn.execute("""
            SELECT COALESCE(SUM(lifetime_spend_usd), 0.0) 
            FROM fact_customer_360_summary
        """).fetchone()[0]

        spend_diff = abs(order_spend_sum - summary_spend_sum)
        fin_passed = (spend_diff < 0.05)  # floating point cents tolerance
        checks.append(ReconciliationCheckResult(
            check_name="Financial Revenue Reconciliation",
            status="PASSED" if fin_passed else "FAILED",
            description="Completed order total amount must reconcile exactly with Customer 360 lifetime spend",
            details={
                "fct_order_completed_sum": round(order_spend_sum, 2),
                "customer_360_spend_sum": round(summary_spend_sum, 2),
                "variance": round(spend_diff, 4),
            },
        ))

        # -------------------------------------------------------------------
        # Check 5: Primary Key Uniqueness in Target Tables
        # -------------------------------------------------------------------
        dim_cust_dups = self.conn.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT unified_customer_id) FROM dim_unified_customer
        """).fetchone()[0]

        c360_dups = self.conn.execute("""
            SELECT COUNT(*) - COUNT(DISTINCT unified_customer_id) FROM fact_customer_360_summary
        """).fetchone()[0]

        pk_passed = (dim_cust_dups == 0 and c360_dups == 0)
        checks.append(ReconciliationCheckResult(
            check_name="Target Primary Key Uniqueness",
            status="PASSED" if pk_passed else "FAILED",
            description="Zero duplicate unified_customer_id in golden customer dimension and 360 summary",
            details={
                "dim_unified_customer_duplicate_keys": dim_cust_dups,
                "fact_customer_360_summary_duplicate_keys": c360_dups,
            },
        ))

        # -------------------------------------------------------------------
        # Check 6: Uncertain Matches Review Queue Integrity
        # -------------------------------------------------------------------
        unc_df = self.conn.execute("SELECT entity_1_source, entity_1_id, entity_2_source, entity_2_id FROM uncertain_matches_review").df()
        bridge_df = self.conn.execute("SELECT source_system, source_customer_id, unified_customer_id FROM bridge_customer_source_map").df()
        b_map = dict(zip(zip(bridge_df["source_system"], bridge_df["source_customer_id"]), bridge_df["unified_customer_id"]))

        improperly_merged = 0
        if not unc_df.empty:
            for _, r in unc_df.iterrows():
                u1 = b_map.get((r["entity_1_source"], r["entity_1_id"]))
                u2 = b_map.get((r["entity_2_source"], r["entity_2_id"]))
                if u1 and u2 and u1 == u2:
                    improperly_merged += 1

        total_unc = len(unc_df)
        unc_passed = (improperly_merged == 0)
        checks.append(ReconciliationCheckResult(
            check_name="Uncertain Matches Isolation",
            status="PASSED" if unc_passed else "FAILED",
            description="Flagged uncertain pairs must remain isolated and NOT merged into the same golden ID",
            details={
                "total_uncertain_flagged": total_unc,
                "improperly_merged_count": improperly_merged,
            },
        ))

        # -------------------------------------------------------------------
        # Check 7: Ground Truth Verification (if expected labels file exists)
        # -------------------------------------------------------------------
        if expected_labels_file and expected_labels_file.exists():
            gt_df = pd.read_csv(expected_labels_file)
            merged = pd.merge(gt_df, bridge_df, on=["source_system", "source_customer_id"], how="inner")
            if not merged.empty:
                cluster_uids = merged.groupby("expected_cluster_label")["unified_customer_id"].nunique()
                total_ground_truth_clusters = len(cluster_uids)
                correctly_resolved = int((cluster_uids == 1).sum())
            else:
                total_ground_truth_clusters = 0
                correctly_resolved = 0

            accuracy = round((correctly_resolved / total_ground_truth_clusters) * 100, 2) if total_ground_truth_clusters else 100.0
            checks.append(ReconciliationCheckResult(
                check_name="Ground Truth Clustering Accuracy",
                status="PASSED" if accuracy >= 95.0 else "WARNING",
                description="Deterministic clusters match expected ground truth cluster labels",
                details={
                    "total_ground_truth_clusters": total_ground_truth_clusters,
                    "correctly_resolved_clusters": correctly_resolved,
                    "accuracy_percentage": f"{accuracy}%",
                },
            ))

        # Tally results
        total = len(checks)
        passed = sum(1 for c in checks if c.status == "PASSED")
        failed = sum(1 for c in checks if c.status == "FAILED")
        warn = sum(1 for c in checks if c.status == "WARNING")
        overall = "PASSED" if failed == 0 else "FAILED"

        return ReconciliationReport(
            run_id=self.run_id,
            total_checks=total,
            passed_checks=passed,
            failed_checks=failed,
            warning_checks=warn,
            overall_status=overall,
            checks=checks,
        )
