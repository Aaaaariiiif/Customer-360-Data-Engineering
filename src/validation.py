"""
Data Quality Validation and Quarantine Module.
Validates schemas, data formats, business constraints, duplicate keys,
and referential integrity across customer, account, order, and interaction datasets.
Quarantined records are isolated with full raw payload and diagnostic metadata.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from src.schemas import QUARANTINE_REJECTED_RECORDS_COLUMNS

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class QuarantineRecord:
    quarantine_id: str
    run_id: str
    source_table: str
    source_record_id: str
    source_system: str
    rejection_category: str
    rejection_reason: str
    raw_record_json: str
    quarantined_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quarantine_id": self.quarantine_id,
            "run_id": self.run_id,
            "source_table": self.source_table,
            "source_record_id": self.source_record_id,
            "source_system": self.source_system,
            "rejection_category": self.rejection_category,
            "rejection_reason": self.rejection_reason,
            "raw_record_json": self.raw_record_json,
            "quarantined_at": self.quarantined_at,
        }


@dataclass
class ValidationSummary:
    total_input: int = 0
    total_valid: int = 0
    total_quarantined: int = 0
    category_counts: Dict[str, int] = field(default_factory=dict)


class DataValidator:
    """Enforces data quality, business rules, duplicate handling, and referential integrity."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.quarantine_records: List[QuarantineRecord] = []

    def _quarantine(
        self,
        table_name: str,
        record: Dict[str, Any],
        record_id: str,
        source_system: str,
        category: str,
        reason: str,
    ):
        """Helper to create and append a quarantine record."""
        qid = f"QRN_{uuid.uuid4().hex[:12].upper()}"
        now_ts = datetime.now(timezone.utc).isoformat()
        q = QuarantineRecord(
            quarantine_id=qid,
            run_id=self.run_id,
            source_table=table_name,
            source_record_id=str(record_id),
            source_system=str(source_system),
            rejection_category=category,
            rejection_reason=reason,
            raw_record_json=json.dumps(record, default=str),
            quarantined_at=now_ts,
        )
        self.quarantine_records.append(q)

    def _is_valid_iso_timestamp(self, ts_str: Any) -> bool:
        if not ts_str or not isinstance(ts_str, str):
            return False
        try:
            # Handle ISO formats including trailing Z
            clean = ts_str.replace("Z", "+00:00")
            datetime.fromisoformat(clean)
            return True
        except (ValueError, TypeError):
            return False

    def validate_customers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validates customers table and separates clean records from rejects."""
        if df.empty:
            return pd.DataFrame(columns=df.columns)

        valid_rows: List[Dict[str, Any]] = []
        seen_keys: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for _, row in df.iterrows():
            r = row.to_dict()
            src_sys = str(r.get("source_system", "")).strip()
            cid = str(r.get("source_customer_id", "")).strip()
            fn = str(r.get("first_name", "")).strip()
            ln = str(r.get("last_name", "")).strip()
            email = str(r.get("email", "")).strip()
            phone = str(r.get("phone", "")).strip()
            tax_id = str(r.get("tax_id", "")).strip()

            # 1. Missing Mandatory Fields
            if not src_sys or not cid:
                self._quarantine("customers", r, cid, src_sys, "MISSING_REQUIRED_FIELD", "Missing source_system or source_customer_id")
                continue
            if not fn or not ln:
                self._quarantine("customers", r, cid, src_sys, "MISSING_REQUIRED_FIELD", "Missing mandatory first_name or last_name")
                continue

            # 2. At least one contact info requirement
            if not email and not phone and not tax_id:
                self._quarantine("customers", r, cid, src_sys, "MISSING_REQUIRED_FIELD", "Customer has no contact information (email, phone, tax_id all empty)")
                continue

            # 3. Format Validation (Email format if present)
            if email and not EMAIL_REGEX.match(email):
                self._quarantine("customers", r, cid, src_sys, "MALFORMED_INPUT", f"Invalid email format: '{email}'")
                continue

            # 4. Duplicate Key in Batch Check
            key = (src_sys, cid)
            if key in seen_keys:
                existing = seen_keys[key]
                # Compare critical fields to check conflict vs identical duplicate
                if (existing.get("first_name") == fn and
                    existing.get("last_name") == ln and
                    existing.get("email") == email):
                    # Identical duplicate -> skip silently to maintain idempotency
                    continue
                else:
                    self._quarantine("customers", r, cid, src_sys, "DUPLICATE_KEY_CONFLICT", f"Conflicting duplicate record for customer key {key}")
                    continue

            seen_keys[key] = r
            valid_rows.append(r)

        return pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns)

    def validate_accounts(self, df: pd.DataFrame, valid_customer_keys: Set[Tuple[str, str]], valid_customer_ids: Set[str]) -> pd.DataFrame:
        """Validates accounts table and checks referential integrity against valid customers."""
        if df.empty:
            return pd.DataFrame(columns=df.columns)

        valid_rows: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for _, row in df.iterrows():
            r = row.to_dict()
            src_sys = str(r.get("source_system", "")).strip()
            aid = str(r.get("account_id", "")).strip()
            cid = str(r.get("source_customer_id", "")).strip()
            atype = str(r.get("account_type", "")).strip()
            status = str(r.get("status", "")).strip()
            curr = str(r.get("currency", "")).strip()

            # 1. Missing Mandatory Fields
            if not src_sys or not aid or not cid:
                self._quarantine("accounts", r, aid, src_sys, "MISSING_REQUIRED_FIELD", "Missing source_system, account_id, or source_customer_id")
                continue
            if not atype:
                self._quarantine("accounts", r, aid, src_sys, "MISSING_REQUIRED_FIELD", "Missing mandatory account_type")
                continue
            if not status or not curr:
                self._quarantine("accounts", r, aid, src_sys, "MISSING_REQUIRED_FIELD", "Missing mandatory status or currency")
                continue

            # 2. Referential Integrity: Check parent customer exists
            # Either exact (source_system, source_customer_id) or global customer_id
            if (src_sys, cid) not in valid_customer_keys and cid not in valid_customer_ids:
                self._quarantine(
                    "accounts",
                    r,
                    aid,
                    src_sys,
                    "REFERENTIAL_INTEGRITY_VIOLATION",
                    f"Orphan account: parent customer '{cid}' not found in valid customers",
                )
                continue

            # 3. Duplicate Key
            key = (src_sys, aid)
            if key in seen_keys:
                continue  # Identical duplicate in batch skipped
            seen_keys.add(key)

            # Balance parse check
            bal_str = str(r.get("balance", "0")).strip()
            try:
                r["balance"] = float(bal_str) if bal_str else 0.0
            except ValueError:
                self._quarantine("accounts", r, aid, src_sys, "MALFORMED_INPUT", f"Invalid account balance value: '{bal_str}'")
                continue

            valid_rows.append(r)

        return pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns)

    def validate_orders(self, df: pd.DataFrame, valid_account_ids: Set[str]) -> pd.DataFrame:
        """Validates orders table and checks referential integrity against valid accounts."""
        if df.empty:
            return pd.DataFrame(columns=df.columns)

        valid_rows: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for _, row in df.iterrows():
            r = row.to_dict()
            src_sys = str(r.get("source_system", "")).strip()
            oid = str(r.get("order_id", "")).strip()
            aid = str(r.get("account_id", "")).strip()
            ots = str(r.get("order_timestamp", "")).strip()
            amt_str = str(r.get("total_amount", "")).strip()
            status = str(r.get("status", "")).strip()

            # 1. Missing Mandatory Fields
            if not src_sys or not oid or not aid:
                self._quarantine("orders", r, oid, src_sys, "MISSING_REQUIRED_FIELD", "Missing source_system, order_id, or account_id")
                continue

            # 2. Timestamp Validation
            if not self._is_valid_iso_timestamp(ots):
                self._quarantine("orders", r, oid, src_sys, "MALFORMED_INPUT", f"Invalid ISO-8601 order timestamp: '{ots}'")
                continue

            # 3. Referential Integrity: Check parent account exists
            if aid not in valid_account_ids:
                self._quarantine(
                    "orders",
                    r,
                    oid,
                    src_sys,
                    "REFERENTIAL_INTEGRITY_VIOLATION",
                    f"Orphan order: parent account '{aid}' not found in valid accounts",
                )
                continue

            # 4. Numeric Parse & Value Range
            try:
                amt = float(amt_str)
                r["total_amount"] = amt
            except ValueError:
                self._quarantine("orders", r, oid, src_sys, "MALFORMED_INPUT", f"Invalid total_amount numeric value: '{amt_str}'")
                continue

            # Item count parse
            item_cnt_str = str(r.get("item_count", "1")).strip()
            try:
                r["item_count"] = int(item_cnt_str)
            except ValueError:
                r["item_count"] = 1

            # 5. Duplicate Key
            key = (src_sys, oid)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            valid_rows.append(r)

        return pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns)

    def validate_interactions(
        self,
        df: pd.DataFrame,
        valid_customer_keys: Set[Tuple[str, str]],
        valid_customer_ids: Set[str],
    ) -> pd.DataFrame:
        """Validates interactions table, checks sentiment bounds and referential integrity."""
        if df.empty:
            return pd.DataFrame(columns=df.columns)

        valid_rows: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for _, row in df.iterrows():
            r = row.to_dict()
            src_sys = str(r.get("source_system", "")).strip()
            iid = str(r.get("interaction_id", "")).strip()
            cid = str(r.get("source_customer_id", "")).strip()
            its = str(r.get("interaction_timestamp", "")).strip()
            channel = str(r.get("channel", "")).strip()
            itype = str(r.get("interaction_type", "")).strip()
            sent_str = str(r.get("sentiment_score", "0.0")).strip()
            dur_str = str(r.get("duration_seconds", "0")).strip()

            # 1. Missing Mandatory Fields
            if not src_sys or not iid or not cid:
                self._quarantine("interactions", r, iid, src_sys, "MISSING_REQUIRED_FIELD", "Missing source_system, interaction_id, or source_customer_id")
                continue
            if not channel or not itype:
                self._quarantine("interactions", r, iid, src_sys, "MISSING_REQUIRED_FIELD", "Missing mandatory channel or interaction_type")
                continue

            # 2. Timestamp Validation
            if not self._is_valid_iso_timestamp(its):
                self._quarantine("interactions", r, iid, src_sys, "MALFORMED_INPUT", f"Invalid interaction timestamp: '{its}'")
                continue

            # 3. Referential Integrity Check
            if (src_sys, cid) not in valid_customer_keys and cid not in valid_customer_ids:
                self._quarantine(
                    "interactions",
                    r,
                    iid,
                    src_sys,
                    "REFERENTIAL_INTEGRITY_VIOLATION",
                    f"Orphan interaction: parent customer '{cid}' not found in valid customers",
                )
                continue

            # 4. Sentiment Score Range Check: [-1.0, 1.0]
            try:
                sentiment = float(sent_str)
                if sentiment < -1.0 or sentiment > 1.0:
                    self._quarantine(
                        "interactions",
                        r,
                        iid,
                        src_sys,
                        "OUT_OF_BOUNDS_VALUE",
                        f"Sentiment score {sentiment} outside valid range [-1.0, 1.0]",
                    )
                    continue
                r["sentiment_score"] = sentiment
            except ValueError:
                self._quarantine("interactions", r, iid, src_sys, "MALFORMED_INPUT", f"Invalid sentiment_score numeric format: '{sent_str}'")
                continue

            # Duration check
            try:
                dur = int(dur_str)
                r["duration_seconds"] = max(0, dur)
            except ValueError:
                r["duration_seconds"] = 0

            # 5. Duplicate Key
            key = (src_sys, iid)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            valid_rows.append(r)

        return pd.DataFrame(valid_rows) if valid_rows else pd.DataFrame(columns=df.columns)

    def validate_all(
        self,
        raw_tables: Dict[str, pd.DataFrame],
    ) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
        """
        Runs comprehensive data quality validation across all entities in topological order:
        Customers -> Accounts -> Orders & Interactions.
        Returns:
            - Dict of cleaned/valid DataFrames for each entity
            - Consolidated quarantine DataFrame
        """
        # 1. Customers
        clean_customers = self.validate_customers(raw_tables.get("customers", pd.DataFrame()))

        # Build sets of valid customer keys for referential integrity
        valid_cust_keys: Set[Tuple[str, str]] = set()
        valid_cust_ids: Set[str] = set()
        if not clean_customers.empty:
            for _, r in clean_customers.iterrows():
                valid_cust_keys.add((str(r["source_system"]), str(r["source_customer_id"])))
                valid_cust_ids.add(str(r["source_customer_id"]))

        # 2. Accounts
        clean_accounts = self.validate_accounts(
            raw_tables.get("accounts", pd.DataFrame()),
            valid_cust_keys,
            valid_cust_ids,
        )

        # Build set of valid account IDs
        valid_account_ids: Set[str] = set()
        if not clean_accounts.empty:
            for _, r in clean_accounts.iterrows():
                valid_account_ids.add(str(r["account_id"]))

        # 3. Orders
        clean_orders = self.validate_orders(
            raw_tables.get("orders", pd.DataFrame()),
            valid_account_ids,
        )

        # 4. Interactions
        clean_interactions = self.validate_interactions(
            raw_tables.get("interactions", pd.DataFrame()),
            valid_cust_keys,
            valid_cust_ids,
        )

        clean_tables = {
            "customers": clean_customers,
            "accounts": clean_accounts,
            "orders": clean_orders,
            "interactions": clean_interactions,
        }

        # Convert quarantine list to DataFrame
        if self.quarantine_records:
            q_dicts = [q.to_dict() for q in self.quarantine_records]
            quarantine_df = pd.DataFrame(q_dicts)
        else:
            quarantine_df = pd.DataFrame(columns=QUARANTINE_REJECTED_RECORDS_COLUMNS)

        return clean_tables, quarantine_df
