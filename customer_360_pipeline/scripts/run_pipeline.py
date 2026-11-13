#!/usr/bin/env python3
"""
CLI runner for the Customer 360 & Entity Resolution Pipeline.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PipelineConfig
from src.pipeline import Customer360Pipeline


def main():
    parser = argparse.ArgumentParser(description="Customer 360 Unified Pipeline CLI")
    parser.add_argument("--config", type=str, default="config/pipeline_config.yaml", help="Path to config YAML")
    parser.add_argument("--input-dir", type=str, default=None, help="Path to input data directory")
    parser.add_argument("--output-dir", type=str, default=None, help="Path to output target directory")
    parser.add_argument("--run-id", type=str, default=None, help="Unique pipeline run identifier")
    parser.add_argument("--mode", type=str, choices=["overwrite", "upsert", "append"], default=None, help="Target load mode")
    parser.add_argument("--duckdb-path", type=str, default=None, help="Path to DuckDB database file")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    config = PipelineConfig.from_yaml(cfg_path) if cfg_path.exists() else PipelineConfig()

    pipeline = Customer360Pipeline(config=config)
    result = pipeline.run(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        run_id=args.run_id,
        mode=args.mode,
        duckdb_path=args.duckdb_path,
    )

    print("\n" + "=" * 70)
    print(f"PIPELINE RUN FINISHED: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Execution Duration: {result.metrics.duration_seconds:.2f} seconds")
    print(f"Input Rows Processed: {result.metrics.total_input_rows:,}")
    print(f"Valid Rows: {result.metrics.total_valid_rows:,}")
    print(f"Quarantined Records: {result.metrics.total_quarantined_rows:,}")
    print(f"Golden Master Customers: {result.metrics.total_golden_customers:,}")
    print(f"Uncertain Matches Flagged: {result.metrics.total_uncertain_matches:,}")
    print("=" * 70 + "\n")

    if result.status != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
