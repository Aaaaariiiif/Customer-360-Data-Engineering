"""
Configuration management module.
Loads settings from YAML files or environment variables with strict typing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


@dataclass
class SourceSystemConfig:
    name: str
    priority: int
    reliability: float = 0.90


@dataclass
class EntityResolutionRuleConfig:
    enabled: bool = True
    rule_id: str = ""
    confidence: float = 1.0


@dataclass
class UncertainThresholdsConfig:
    similarity_min: float = 0.70
    similarity_max: float = 0.87
    flag_shared_phone_different_name: bool = True
    flag_same_address_different_first_name: bool = True


@dataclass
class EntityResolutionConfig:
    blocking_keys: List[str] = field(default_factory=lambda: ["tax_id", "email", "phone", "postal_code"])
    rules: Dict[str, EntityResolutionRuleConfig] = field(default_factory=dict)
    uncertain_thresholds: UncertainThresholdsConfig = field(default_factory=UncertainThresholdsConfig)


@dataclass
class ValidationConfig:
    strict_schema: bool = True
    quarantine_orphans: bool = True
    quarantine_malformed: bool = True
    quarantine_duplicates: bool = True
    max_error_rate_percent: float = 50.0


@dataclass
class ExecutionConfig:
    batch_size: int = 50000
    write_mode: str = "overwrite"  # overwrite | append | upsert
    export_formats: List[str] = field(default_factory=lambda: ["duckdb", "parquet", "csv"])


@dataclass
class PathsConfig:
    input_dir: str = "data/sample"
    output_dir: str = "data/output"
    expected_labels_dir: str = "data/expected_labels"
    duckdb_path: str = "data/output/customer_360.duckdb"
    parquet_dir: str = "data/output/parquet"
    quarantine_dir: str = "data/output/quarantine"
    audit_dir: str = "data/output/audit"


@dataclass
class PipelineConfig:
    name: str = "customer_360_unified_pipeline"
    version: str = "1.0.0"
    environment: str = "local"
    paths: PathsConfig = field(default_factory=PathsConfig)
    source_systems: Dict[str, SourceSystemConfig] = field(default_factory=dict)
    entity_resolution: EntityResolutionConfig = field(default_factory=EntityResolutionConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> PipelineConfig:
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        paths_data = data.get("paths", {})
        paths = PathsConfig(
            input_dir=paths_data.get("input_dir", "data/sample"),
            output_dir=paths_data.get("output_dir", "data/output"),
            expected_labels_dir=paths_data.get("expected_labels_dir", "data/expected_labels"),
            duckdb_path=paths_data.get("duckdb_path", "data/output/customer_360.duckdb"),
            parquet_dir=paths_data.get("parquet_dir", "data/output/parquet"),
            quarantine_dir=paths_data.get("quarantine_dir", "data/output/quarantine"),
            audit_dir=paths_data.get("audit_dir", "data/output/audit"),
        )

        source_systems_data = data.get("source_systems", {})
        source_systems = {}
        for k, v in source_systems_data.items():
            source_systems[k] = SourceSystemConfig(
                name=v.get("name", k),
                priority=v.get("priority", 99),
                reliability=v.get("reliability", 0.9),
            )

        er_data = data.get("entity_resolution", {})
        rules_data = er_data.get("rules", {})
        rules = {}
        for rk, rv in rules_data.items():
            rules[rk] = EntityResolutionRuleConfig(
                enabled=rv.get("enabled", True),
                rule_id=rv.get("rule_id", rk),
                confidence=float(rv.get("confidence", 1.0)),
            )

        thresh_data = er_data.get("uncertain_thresholds", {})
        thresholds = UncertainThresholdsConfig(
            similarity_min=float(thresh_data.get("similarity_min", 0.70)),
            similarity_max=float(thresh_data.get("similarity_max", 0.87)),
            flag_shared_phone_different_name=thresh_data.get("flag_shared_phone_different_name", True),
            flag_same_address_different_first_name=thresh_data.get("flag_same_address_different_first_name", True),
        )

        er_config = EntityResolutionConfig(
            blocking_keys=er_data.get("blocking_keys", ["tax_id", "email", "phone", "postal_code"]),
            rules=rules,
            uncertain_thresholds=thresholds,
        )

        val_data = data.get("validation", {})
        validation = ValidationConfig(
            strict_schema=val_data.get("strict_schema", True),
            quarantine_orphans=val_data.get("quarantine_orphans", True),
            quarantine_malformed=val_data.get("quarantine_malformed", True),
            quarantine_duplicates=val_data.get("quarantine_duplicates", True),
            max_error_rate_percent=float(val_data.get("max_error_rate_percent", 50.0)),
        )

        exec_data = data.get("execution", {})
        execution = ExecutionConfig(
            batch_size=int(exec_data.get("batch_size", 50000)),
            write_mode=exec_data.get("write_mode", "overwrite"),
            export_formats=exec_data.get("export_formats", ["duckdb", "parquet", "csv"]),
        )

        p_info = data.get("pipeline", {})
        return cls(
            name=p_info.get("name", "customer_360_unified_pipeline"),
            version=p_info.get("version", "1.0.0"),
            environment=p_info.get("environment", "local"),
            paths=paths,
            source_systems=source_systems,
            entity_resolution=er_config,
            validation=validation,
            execution=execution,
        )
