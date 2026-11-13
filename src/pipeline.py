"""
Master Pipeline Orchestrator for Customer 360 & Entity Resolution.
Ties Ingestion, Validation, Entity Resolution, Transformation, Target Publishing,
Observability, and Automated Reconciliation into a unified, reproducible workflow.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.config import PipelineConfig
from src.entity_resolution import EntityResolutionEngine
from src.ingestion import IngestionEngine
from src.observability import PipelineMetrics, PipelineObserver
from src.reconciliation import ReconciliationEngine, ReconciliationReport
from src.storage import StorageManager
from src.transformation import Customer360Transformer
from src.validation import DataValidator


@dataclass
class PipelineResult:
    run_id: str
    status: str
    metrics: PipelineMetrics
    reconciliation_report: ReconciliationReport
    target_tables: Dict[str, pd.DataFrame]
    quarantine_df: pd.DataFrame
    uncertain_df: pd.DataFrame


class Customer360Pipeline:
    """Master orchestrator for the Customer 360 unified data pipeline."""

    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()

    def run(
        self,
        input_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        run_id: Optional[str] = None,
        mode: Optional[str] = None,
        duckdb_path: Optional[str] = None,
    ) -> PipelineResult:
        """
        Executes the full end-to-end pipeline:
        1. Ingestion -> 2. Validation -> 3. Entity Resolution -> 4. Transformation ->
        5. Publishing -> 6. Reconciliation -> 7. Audit & Lineage
        """
        # Resolve parameters from config or arguments
        in_dir = Path(input_dir or self.config.paths.input_dir)
        out_dir = Path(output_dir or self.config.paths.output_dir)
        write_mode = mode or self.config.execution.write_mode
        active_run_id = run_id or f"RUN_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6].upper()}"
        active_duckdb = duckdb_path or self.config.paths.duckdb_path

        observer = PipelineObserver(
            run_id=active_run_id,
            audit_dir=str(out_dir / "audit"),
        )
        logger = observer.logger
        logger.info(f"Starting Customer 360 Pipeline. Input: {in_dir}, Output: {out_dir}, Mode: {write_mode}")

        try:
            # ---------------------------------------------------------------
            # 1. Ingestion Layer
            # ---------------------------------------------------------------
            logger.info("Executing Ingestion Layer...")
            ingestion_engine = IngestionEngine(run_id=active_run_id)
            ingested_datasets = ingestion_engine.ingest_all(in_dir)

            raw_tables = {k: v.df for k, v in ingested_datasets.items()}
            input_counts = {k: v.row_count for k, v in ingested_datasets.items()}
            observer.record_input_counts(input_counts)

            # ---------------------------------------------------------------
            # 2. Validation & Quarantine Layer
            # ---------------------------------------------------------------
            logger.info("Executing Validation & Quarantine Layer...")
            validator = DataValidator(run_id=active_run_id)
            clean_tables, quarantine_df = validator.validate_all(raw_tables)

            valid_counts = {k: len(v) for k, v in clean_tables.items()}
            quarantine_counts = {}
            if not quarantine_df.empty:
                q_counts = quarantine_df["source_table"].value_counts().to_dict()
                for entity in ["customers", "accounts", "orders", "interactions"]:
                    quarantine_counts[entity] = int(q_counts.get(entity, 0))
            else:
                quarantine_counts = {k: 0 for k in ["customers", "accounts", "orders", "interactions"]}

            observer.record_validation_counts(valid_counts, quarantine_counts)

            # ---------------------------------------------------------------
            # 3. Entity Resolution & Deduplication Layer
            # ---------------------------------------------------------------
            logger.info("Executing Deterministic Entity Resolution & Identity Stitching...")
            er_engine = EntityResolutionEngine(
                run_id=active_run_id,
                system_priority={k: v.priority for k, v in self.config.source_systems.items()}
                if self.config.source_systems
                else None,
                uncertain_similarity_range=(
                    self.config.entity_resolution.uncertain_thresholds.similarity_min,
                    self.config.entity_resolution.uncertain_thresholds.similarity_max,
                ),
            )

            dim_unified_customer, bridge_customer_source_map, uncertain_matches_df = (
                er_engine.resolve_entities(clean_tables["customers"])
            )

            # ---------------------------------------------------------------
            # 4. Transformation & Customer 360 Metrics Layer
            # ---------------------------------------------------------------
            logger.info("Computing Customer 360 Feature Store and Dimensional Views...")
            transformer = Customer360Transformer(run_id=active_run_id)
            dim_account_unified, fct_order_unified, fct_interaction_unified, fact_customer_360_summary = (
                transformer.transform(
                    clean_customers=clean_tables["customers"],
                    clean_accounts=clean_tables["accounts"],
                    clean_orders=clean_tables["orders"],
                    clean_interactions=clean_tables["interactions"],
                    dim_unified_customer=dim_unified_customer,
                    bridge_customer_source_map=bridge_customer_source_map,
                )
            )

            # ---------------------------------------------------------------
            # 5. Target Publishing Layer
            # ---------------------------------------------------------------
            logger.info("Publishing Target, Quarantine, and Audit Datasets...")
            storage = StorageManager(
                duckdb_path=active_duckdb,
                parquet_dir=out_dir / "parquet",
                csv_dir=out_dir,
            )

            tables_to_publish = {
                "dim_unified_customer": dim_unified_customer,
                "bridge_customer_source_map": bridge_customer_source_map,
                "dim_account_unified": dim_account_unified,
                "fct_order_unified": fct_order_unified,
                "fct_interaction_unified": fct_interaction_unified,
                "fact_customer_360_summary": fact_customer_360_summary,
                "quarantine_rejected_records": quarantine_df,
                "uncertain_matches_review": uncertain_matches_df,
            }

            storage.publish_all(
                tables_to_publish,
                mode=write_mode,
                run_id=active_run_id,
                formats=self.config.execution.export_formats,
            )

            target_counts = {k: len(v) for k, v in tables_to_publish.items()}
            observer.record_target_counts(
                target_counts=target_counts,
                golden_customers=len(dim_unified_customer),
                uncertain_matches=len(uncertain_matches_df),
            )

            # ---------------------------------------------------------------
            # 6. Automated Reconciliation & Audit Layer
            # ---------------------------------------------------------------
            logger.info("Executing Automated Reconciliation Engine...")
            recon_conn = storage.get_connection()
            try:
                recon_engine = ReconciliationEngine(duckdb_conn=recon_conn, run_id=active_run_id)
                expected_labels_file = in_dir.parent / "expected_labels" / "expected_golden_customers.csv"
                if not expected_labels_file.exists():
                    expected_labels_file = Path(self.config.paths.expected_labels_dir) / "expected_golden_customers.csv"

                reconciliation_report = recon_engine.run_all_checks(
                    input_counts=input_counts,
                    valid_counts=valid_counts,
                    quarantine_counts=quarantine_counts,
                    expected_labels_file=expected_labels_file if expected_labels_file.exists() else None,
                )
            finally:
                recon_conn.close()

            # Write Reconciliation Report to Disk
            recon_md_file = out_dir / "audit" / f"reconciliation_report_{active_run_id}.md"
            with open(recon_md_file, "w", encoding="utf-8") as f:
                f.write(reconciliation_report.to_markdown())

            # Also write latest report for easy reviewer reference
            with open(out_dir / "reconciliation_report.md", "w", encoding="utf-8") as f:
                f.write(reconciliation_report.to_markdown())

            # ---------------------------------------------------------------
            # 7. Complete Observability & Persist Run Audit Table
            # ---------------------------------------------------------------
            metrics = observer.mark_completed(
                status=reconciliation_report.overall_status,
                error_message="" if reconciliation_report.overall_status == "PASSED" else "Reconciliation check failed",
            )

            # Persist audit metrics to DuckDB table
            storage.publish_table(
                "pipeline_run_audit",
                metrics.to_df(),
                mode="append",
                run_id=active_run_id,
            )

            return PipelineResult(
                run_id=active_run_id,
                status=metrics.status,
                metrics=metrics,
                reconciliation_report=reconciliation_report,
                target_tables=tables_to_publish,
                quarantine_df=quarantine_df,
                uncertain_df=uncertain_matches_df,
            )

        except Exception as e:
            logger.exception(f"Pipeline failed with exception: {e}")
            metrics = observer.mark_completed(status="FAILED", error_message=str(e))
            raise e
        finally:
            observer.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Customer 360 Data Pipeline")
    parser.add_argument("--config", type=str, default="config/pipeline_config.yaml", help="Path to YAML config")
    parser.add_argument("--input-dir", type=str, default=None, help="Input directory containing raw CSVs")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for target datasets")
    parser.add_argument("--run-id", type=str, default=None, help="Explicit run ID")
    parser.add_argument("--mode", type=str, choices=["overwrite", "upsert", "append"], default="overwrite", help="Target write mode")
    parser.add_argument("--duckdb-path", type=str, default=None, help="DuckDB database path")
    return parser.parse_args()


def main():
    args = parse_args()
    config = PipelineConfig.from_yaml(args.config) if Path(args.config).exists() else PipelineConfig()
    pipeline = Customer360Pipeline(config=config)
    result = pipeline.run(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        run_id=args.run_id,
        mode=args.mode,
        duckdb_path=args.duckdb_path,
    )
    print("\n" + "=" * 70)
    print(f"PIPELINE EXECUTION COMPLETED: Status = {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Duration: {result.metrics.duration_seconds:.2f}s")
    print(f"Golden Customers Created: {result.metrics.total_golden_customers}")
    print(f"Uncertain Matches Flagged: {result.metrics.total_uncertain_matches}")
    print(f"Quarantined Records: {result.metrics.total_quarantined_rows}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
