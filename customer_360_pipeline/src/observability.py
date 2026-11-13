"""
Observability and Pipeline Audit Module.
Tracks execution metrics, row counts, quarantine tallies, error messages,
and persists audit logs to both JSON files and the target database.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
import pandas as pd

from src.schemas import PIPELINE_RUN_AUDIT_COLUMNS


@dataclass
class PipelineMetrics:
    run_id: str
    batch_id: str = ""
    status: str = "STARTED"
    start_time: str = ""
    end_time: str = ""
    duration_seconds: float = 0.0
    total_input_rows: int = 0
    total_valid_rows: int = 0
    total_quarantined_rows: int = 0
    total_golden_customers: int = 0
    total_uncertain_matches: int = 0
    input_counts: Dict[str, int] = field(default_factory=dict)
    valid_counts: Dict[str, int] = field(default_factory=dict)
    quarantined_counts: Dict[str, int] = field(default_factory=dict)
    target_counts: Dict[str, int] = field(default_factory=dict)
    error_message: str = ""

    def to_df(self) -> pd.DataFrame:
        row = {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "total_input_rows": self.total_input_rows,
            "total_valid_rows": self.total_valid_rows,
            "total_quarantined_rows": self.total_quarantined_rows,
            "total_golden_customers": self.total_golden_customers,
            "total_uncertain_matches": self.total_uncertain_matches,
            "input_counts_json": json.dumps(self.input_counts),
            "valid_counts_json": json.dumps(self.valid_counts),
            "quarantined_counts_json": json.dumps(self.quarantined_counts),
            "target_counts_json": json.dumps(self.target_counts),
            "error_message": self.error_message,
        }
        return pd.DataFrame([row], columns=PIPELINE_RUN_AUDIT_COLUMNS)


class PipelineObserver:
    """Provides structured logging and operational metrics collection."""

    def __init__(self, run_id: str, batch_id: str = "", audit_dir: str = "data/output/audit"):
        self.run_id = run_id
        self.batch_id = batch_id or f"BATCH_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.audit_dir = Path(audit_dir)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self.start_dt = datetime.now(timezone.utc)
        self.metrics = PipelineMetrics(
            run_id=self.run_id,
            batch_id=self.batch_id,
            status="STARTED",
            start_time=self.start_dt.isoformat(),
        )

        self.logger = self._setup_logger()
        self.logger.info(f"Pipeline initialized. Run ID: {self.run_id}, Batch ID: {self.batch_id}")

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"Pipeline_{self.run_id}")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # File handler
        log_file = self.audit_dir / f"pipeline_run_{self.run_id}.log"
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        return logger

    def record_input_counts(self, counts: Dict[str, int]):
        self.metrics.input_counts = counts
        self.metrics.total_input_rows = sum(counts.values())
        self.logger.info(f"Input row counts: {counts} (Total: {self.metrics.total_input_rows})")

    def record_validation_counts(self, valid_counts: Dict[str, int], quarantined_counts: Dict[str, int]):
        self.metrics.valid_counts = valid_counts
        self.metrics.quarantined_counts = quarantined_counts
        self.metrics.total_valid_rows = sum(valid_counts.values())
        self.metrics.total_quarantined_rows = sum(quarantined_counts.values())
        self.logger.info(f"Valid row counts: {valid_counts} (Total: {self.metrics.total_valid_rows})")
        self.logger.info(f"Quarantined row counts: {quarantined_counts} (Total: {self.metrics.total_quarantined_rows})")

    def record_target_counts(
        self,
        target_counts: Dict[str, int],
        golden_customers: int,
        uncertain_matches: int,
    ):
        self.metrics.target_counts = target_counts
        self.metrics.total_golden_customers = golden_customers
        self.metrics.total_uncertain_matches = uncertain_matches
        self.logger.info(
            f"Target published counts: {target_counts}. Golden customers: {golden_customers}, Uncertain matches: {uncertain_matches}"
        )

    def mark_completed(self, status: str = "SUCCESS", error_message: str = "") -> PipelineMetrics:
        end_dt = datetime.now(timezone.utc)
        self.metrics.end_time = end_dt.isoformat()
        self.metrics.duration_seconds = round((end_dt - self.start_dt).total_seconds(), 3)
        self.metrics.status = status
        self.metrics.error_message = error_message

        # Persist summary JSON
        summary_file = self.audit_dir / f"run_summary_{self.run_id}.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(asdict(self.metrics), f, indent=2)

        self.logger.info(
            f"Pipeline run finished with status: {status} in {self.metrics.duration_seconds:.2f}s. Summary written to {summary_file}"
        )
        return self.metrics

    def close(self):
        """Closes all logging handlers to release file locks (critical on Windows)."""
        for handler in list(self.logger.handlers):
            try:
                handler.flush()
                handler.close()
                self.logger.removeHandler(handler)
            except Exception:
                pass
