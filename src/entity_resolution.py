"""
Deterministic Entity Resolution and Identity Stitching Module.
Implements:
1. Standardized field normalization (phones, emails, addresses, names)
2. Scalable hash-indexed blocking for O(N) candidate generation
3. Documented deterministic matching tiers (Tax ID, Email, Phone+Name, Name+Address)
4. Detection of uncertain matches (shared phone/household) flagged for human review
5. Disjoint-set graph clustering for connected components
6. Deterministic, collision-resistant Golden Customer ID generation
7. Attribute survivorship based on source system priority, recency, and completeness
8. Complete source-to-target lineage mapping
"""

from __future__ import annotations

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd

from src.schemas import (
    DIM_UNIFIED_CUSTOMER_COLUMNS,
    BRIDGE_CUSTOMER_SOURCE_MAP_COLUMNS,
    UNCERTAIN_MATCHES_REVIEW_COLUMNS,
)

# Address abbreviations map for standardizing physical addresses
ADDR_ABBREVIATIONS = {
    "st": "street",
    "ave": "avenue",
    "rd": "road",
    "dr": "drive",
    "ln": "lane",
    "blvd": "boulevard",
    "ct": "court",
    "apt": "apartment",
    "ste": "suite",
    "fl": "floor",
    "pkwy": "parkway",
}

DEFAULT_SYSTEM_PRIORITY = {
    "CRM_NORTH_AMERICA": 1,
    "CRM_EUROPE": 2,
    "BILLING_CORE": 3,
    "WEB_STORE": 4,
    "SUPPORT_DESK": 5,
}


class DisjointSet:
    """Disjoint-set (Union-Find) data structure with path compression."""

    def __init__(self):
        self.parent: Dict[str, str] = {}
        self.rank: Dict[str, int] = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0
            return item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, x: str, y: str):
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x == root_y:
            return
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1


class EntityResolutionEngine:
    """Deterministic entity resolution and survivorship engine."""

    def __init__(
        self,
        run_id: str,
        system_priority: Optional[Dict[str, int]] = None,
        uncertain_similarity_range: Tuple[float, float] = (0.70, 0.87),
    ):
        self.run_id = run_id
        self.system_priority = system_priority or DEFAULT_SYSTEM_PRIORITY
        self.sim_min, self.sim_max = uncertain_similarity_range
        self.uncertain_reviews: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------------
    # Field Normalizers
    # -----------------------------------------------------------------------
    @staticmethod
    def normalize_name(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        s = str(val).lower().strip()
        # Remove special characters, keep letters and spaces
        s = re.sub(r"[^a-z\s]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def normalize_email(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        s = str(val).lower().strip()
        return s

    @staticmethod
    def normalize_phone(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        # Extract digits only
        digits = re.sub(r"\D", "", str(val))
        # If starts with US country code '1' and length 11, strip country code
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits

    @staticmethod
    def normalize_tax_id(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        # Strip hyphens, spaces, and punctuation
        return re.sub(r"[^a-zA-Z0-9]", "", str(val)).upper()

    @staticmethod
    def normalize_address(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        s = str(val).lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        tokens = s.split()
        normalized_tokens = [ADDR_ABBREVIATIONS.get(t, t) for t in tokens]
        return " ".join(normalized_tokens)

    @staticmethod
    def normalize_postal_code(val: Any) -> str:
        if not val or pd.isna(val):
            return ""
        s = re.sub(r"[^\w]", "", str(val)).upper()
        # For US 9-digit zip (123456789), keep first 5 digits
        if len(s) == 9 and s.isdigit():
            return s[:5]
        return s

    @staticmethod
    def string_similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        return difflib.SequenceMatcher(None, s1, s2).ratio()

    # -----------------------------------------------------------------------
    # Deterministic Matching & Blocking
    # -----------------------------------------------------------------------
    def resolve_entities(
        self,
        clean_customers_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Executes deterministic entity resolution:
        1. Normalizes fields
        2. Blocks candidate pairs
        3. Evaluates deterministic match rules
        4. Clusters via DisjointSet
        5. Computes survivorship for Golden Customer records
        6. Emits bridge mapping and uncertain match review records
        """
        if clean_customers_df.empty:
            empty_golden = pd.DataFrame(columns=DIM_UNIFIED_CUSTOMER_COLUMNS)
            empty_bridge = pd.DataFrame(columns=BRIDGE_CUSTOMER_SOURCE_MAP_COLUMNS)
            empty_uncertain = pd.DataFrame(columns=UNCERTAIN_MATCHES_REVIEW_COLUMNS)
            return empty_golden, empty_bridge, empty_uncertain

        df = clean_customers_df.copy()

        # Add normalized columns
        df["norm_fn"] = df["first_name"].apply(self.normalize_name)
        df["norm_ln"] = df["last_name"].apply(self.normalize_name)
        df["norm_full_name"] = df["norm_fn"] + " " + df["norm_ln"]
        df["norm_email"] = df["email"].apply(self.normalize_email)
        df["norm_phone"] = df["phone"].apply(self.normalize_phone)
        df["norm_tax"] = df["tax_id"].apply(self.normalize_tax_id)
        df["norm_addr"] = df["address_line1"].apply(self.normalize_address)
        df["norm_zip"] = df["postal_code"].apply(self.normalize_postal_code)

        # Unique node key for graph: (source_system, source_customer_id)
        df["node_id"] = df["source_system"] + "::" + df["source_customer_id"]

        records = df.to_dict(orient="records")
        record_map = {r["node_id"]: r for r in records}

        # -------------------------------------------------------------------
        # Blocking Buckets
        # -------------------------------------------------------------------
        tax_blocks: Dict[str, List[str]] = {}
        email_blocks: Dict[str, List[str]] = {}
        phone_blocks: Dict[str, List[str]] = {}
        addr_zip_blocks: Dict[str, List[str]] = {}
        zip_blocks: Dict[str, List[str]] = {}

        for r in records:
            nid = r["node_id"]
            if r["norm_tax"] and len(r["norm_tax"]) >= 8:
                tax_blocks.setdefault(r["norm_tax"], []).append(nid)
            if r["norm_email"] and "@" in r["norm_email"]:
                email_blocks.setdefault(r["norm_email"], []).append(nid)
            if r["norm_phone"] and len(r["norm_phone"]) >= 7:
                phone_blocks.setdefault(r["norm_phone"], []).append(nid)
            if r["norm_addr"] and r["norm_zip"]:
                addr_zip_blocks.setdefault(f"{r['norm_addr']}::{r['norm_zip']}", []).append(nid)
            if r["norm_zip"]:
                zip_blocks.setdefault(r["norm_zip"], []).append(nid)

        ds = DisjointSet()
        for nid in record_map:
            ds.find(nid)

        match_lineage: Dict[Tuple[str, str], Tuple[str, float]] = {}

        def record_match(node_a: str, node_b: str, rule_name: str, conf: float):
            pair_key = tuple(sorted([node_a, node_b]))
            if pair_key not in match_lineage or match_lineage[pair_key][1] < conf:
                match_lineage[pair_key] = (rule_name, conf)

        # -------------------------------------------------------------------
        # Rule 1: Exact Tax ID Match (Confidence 1.0)
        # -------------------------------------------------------------------
        for tax, nids in tax_blocks.items():
            if len(nids) > 1:
                base = nids[0]
                for other in nids[1:]:
                    ds.union(base, other)
                    record_match(base, other, "RULE_EXACT_TAX_ID", 1.0)

        # -------------------------------------------------------------------
        # Rule 2: Exact Normalized Email Match (Confidence 0.98)
        # -------------------------------------------------------------------
        for email, nids in email_blocks.items():
            if len(nids) > 1:
                base = nids[0]
                for other in nids[1:]:
                    ds.union(base, other)
                    record_match(base, other, "RULE_EXACT_EMAIL", 0.98)

        # -------------------------------------------------------------------
        # Rule 3: Exact Normalized Phone + Last Name Match (Confidence 0.92)
        # & Check for UNCERTAIN Shared Phone (Different Last Name)
        # -------------------------------------------------------------------
        for phone, nids in phone_blocks.items():
            if len(nids) > 1:
                for i in range(len(nids)):
                    for j in range(i + 1, len(nids)):
                        r1 = record_map[nids[i]]
                        r2 = record_map[nids[j]]
                        ln1 = r1["norm_ln"]
                        ln2 = r2["norm_ln"]

                        if ln1 and ln2 and ln1 == ln2:
                            # Match!
                            ds.union(nids[i], nids[j])
                            record_match(nids[i], nids[j], "RULE_EXACT_PHONE_AND_LAST_NAME", 0.92)
                        elif ln1 and ln2 and ln1 != ln2:
                            # Flag Uncertain: Shared Phone, Different Last Name (Roommates/Family)
                            self._flag_uncertain(
                                r1,
                                r2,
                                "UNCERTAIN_SHARED_PHONE_DIFFERENT_NAME",
                                similarity=0.60,
                            )

        # -------------------------------------------------------------------
        # Rule 4: Exact Name + Address Match (Confidence 0.88)
        # & Check for UNCERTAIN Same Address, Different First Name (Family Members)
        # -------------------------------------------------------------------
        for addr_zip, nids in addr_zip_blocks.items():
            if len(nids) > 1:
                for i in range(len(nids)):
                    for j in range(i + 1, len(nids)):
                        r1 = record_map[nids[i]]
                        r2 = record_map[nids[j]]
                        fn1 = r1["norm_fn"]
                        fn2 = r2["norm_fn"]
                        ln1 = r1["norm_ln"]
                        ln2 = r2["norm_ln"]

                        if fn1 and fn2 and ln1 and ln2:
                            if fn1 == fn2 and ln1 == ln2:
                                # Exact match on full name + address
                                ds.union(nids[i], nids[j])
                                record_match(nids[i], nids[j], "RULE_EXACT_NAME_AND_ADDRESS", 0.88)
                            elif ln1 == ln2 and fn1 != fn2:
                                # Flag Uncertain: Same Household, Different First Name
                                self._flag_uncertain(
                                    r1,
                                    r2,
                                    "UNCERTAIN_SAME_ADDRESS_DIFFERENT_FIRST_NAME",
                                    similarity=0.65,
                                )

        # -------------------------------------------------------------------
        # Heuristic 5: Uncertain High Name Similarity with Same Zip Code
        # (Flagged for human review, DO NOT auto-merge)
        # -------------------------------------------------------------------
        for zip_code, nids in zip_blocks.items():
            if 1 < len(nids) <= 20:  # Bound block size to prevent quadratic explosion on dense zips
                for i in range(len(nids)):
                    for j in range(i + 1, len(nids)):
                        nid1, nid2 = nids[i], nids[j]
                        # If already merged in same cluster, skip
                        if ds.find(nid1) == ds.find(nid2):
                            continue

                        r1 = record_map[nid1]
                        r2 = record_map[nid2]
                        name1 = r1["norm_full_name"]
                        name2 = r2["norm_full_name"]

                        if name1 and name2 and name1 != name2:
                            sim = self.string_similarity(name1, name2)
                            if self.sim_min <= sim <= self.sim_max:
                                self._flag_uncertain(
                                    r1,
                                    r2,
                                    "UNCERTAIN_HIGH_NAME_SIMILARITY_SAME_ZIP",
                                    similarity=sim,
                                )

        # -------------------------------------------------------------------
        # Filter Uncertain Reviews: Retain only pairs that are NOT merged
        # -------------------------------------------------------------------
        unmerged_uncertain = []
        for unc in self.uncertain_reviews:
            n1 = unc["entity_1_source"] + "::" + unc["entity_1_id"]
            n2 = unc["entity_2_source"] + "::" + unc["entity_2_id"]
            if ds.find(n1) != ds.find(n2):
                unmerged_uncertain.append(unc)
        self.uncertain_reviews = unmerged_uncertain

        # -------------------------------------------------------------------
        # Connected Components & Survivorship
        # -------------------------------------------------------------------
        clusters: Dict[str, List[Dict[str, Any]]] = {}
        for nid, r in record_map.items():
            root = ds.find(nid)
            clusters.setdefault(root, []).append(r)

        golden_records: List[Dict[str, Any]] = []
        bridge_records: List[Dict[str, Any]] = []

        now_ts = datetime.now(timezone.utc).isoformat()

        for root, members in clusters.items():
            # 1. Deterministic Golden Customer ID:
            # Sort members by canonical key (source_system, source_customer_id)
            sorted_members = sorted(
                members,
                key=lambda m: (m["source_system"], m["source_customer_id"]),
            )
            canonical_seed = sorted_members[0]["source_system"] + "::" + sorted_members[0]["source_customer_id"]
            hash_suffix = hashlib.sha256(canonical_seed.encode("utf-8")).hexdigest()[:16].upper()
            unified_customer_id = f"UC_{hash_suffix}"
            cluster_id = f"CLU_{hash_suffix}"

            # 2. Survivorship: Sort by source system priority, then recency
            def survivorship_key(m: Dict[str, Any]):
                sys_prio = self.system_priority.get(m["source_system"], 99)
                upd_ts = str(m.get("source_updated_at") or "")
                # lower priority number = higher priority; later timestamp = higher priority
                return (sys_prio, -1 * (datetime.fromisoformat(upd_ts.replace("Z", "+00:00")).timestamp() if upd_ts else 0))

            ranked_members = sorted(members, key=survivorship_key)
            primary_rec = ranked_members[0]

            # Coalesce non-empty attributes across ranked records
            def coalesce(field_name: str) -> str:
                for rec in ranked_members:
                    v = str(rec.get(field_name, "")).strip()
                    if v and not pd.isna(v):
                        return v
                return ""

            golden_fn = coalesce("first_name")
            golden_ln = coalesce("last_name")
            golden_email = coalesce("email")
            golden_phone = coalesce("phone")
            golden_addr = coalesce("address_line1")
            golden_city = coalesce("city")
            golden_state = coalesce("state")
            golden_zip = coalesce("postal_code")
            golden_country = coalesce("country")
            golden_dob = coalesce("date_of_birth")
            golden_tax = coalesce("tax_id")

            # Determine dominant match rule for cluster
            if len(members) == 1:
                cluster_rule = "SINGLETON"
                confidence = 1.0
            else:
                # Find highest confidence rule applied among members
                confidence = 0.95
                cluster_rule = "RULE_DETERMINISTIC_MERGE"
                best_conf = 0.0
                for i in range(len(members)):
                    for j in range(i + 1, len(members)):
                        pair = tuple(sorted([members[i]["node_id"], members[j]["node_id"]]))
                        if pair in match_lineage:
                            r_name, r_conf = match_lineage[pair]
                            if r_conf > best_conf:
                                best_conf = r_conf
                                cluster_rule = r_name
                                confidence = r_conf

            golden_records.append({
                "unified_customer_id": unified_customer_id,
                "match_cluster_id": cluster_id,
                "golden_first_name": golden_fn,
                "golden_last_name": golden_ln,
                "golden_email": golden_email,
                "golden_phone": golden_phone,
                "primary_address": golden_addr,
                "primary_city": golden_city,
                "primary_state": golden_state,
                "primary_postal_code": golden_zip,
                "primary_country": golden_country,
                "date_of_birth": golden_dob,
                "tax_id": golden_tax,
                "source_record_count": len(members),
                "confidence_score": confidence,
                "primary_source_system": primary_rec["source_system"],
                "created_at": primary_rec.get("source_created_at") or now_ts,
                "updated_at": primary_rec.get("source_updated_at") or now_ts,
                "run_id": self.run_id,
            })

            # Create bridge records for lineage
            for m in members:
                # Determine individual match rule
                if len(members) == 1:
                    m_rule = "SINGLETON"
                    m_conf = 1.0
                else:
                    m_rule = cluster_rule
                    m_conf = confidence

                map_id = f"MAP_{hashlib.md5((unified_customer_id + m['source_system'] + m['source_customer_id']).encode('utf-8')).hexdigest()[:12].upper()}"
                bridge_records.append({
                    "mapping_id": map_id,
                    "unified_customer_id": unified_customer_id,
                    "source_system": m["source_system"],
                    "source_customer_id": m["source_customer_id"],
                    "match_rule_applied": m_rule,
                    "match_confidence": m_conf,
                    "is_uncertain": False,
                    "source_created_at": str(m.get("source_created_at", "")),
                    "source_updated_at": str(m.get("source_updated_at", "")),
                    "ingested_at": str(m.get("_ingested_at", now_ts)),
                    "run_id": self.run_id,
                })

        golden_df = pd.DataFrame(golden_records, columns=DIM_UNIFIED_CUSTOMER_COLUMNS)
        bridge_df = pd.DataFrame(bridge_records, columns=BRIDGE_CUSTOMER_SOURCE_MAP_COLUMNS)

        if self.uncertain_reviews:
            uncertain_df = pd.DataFrame(self.uncertain_reviews, columns=UNCERTAIN_MATCHES_REVIEW_COLUMNS)
        else:
            uncertain_df = pd.DataFrame(columns=UNCERTAIN_MATCHES_REVIEW_COLUMNS)

        return golden_df, bridge_df, uncertain_df

    def _flag_uncertain(
        self,
        r1: Dict[str, Any],
        r2: Dict[str, Any],
        heuristic: str,
        similarity: float,
    ):
        """Records an uncertain match for human operator review."""
        rev_id = f"REV_{uuid.uuid4().hex[:12].upper()}"
        now_ts = datetime.now(timezone.utc).isoformat()
        self.uncertain_reviews.append({
            "review_id": rev_id,
            "run_id": self.run_id,
            "entity_1_source": r1["source_system"],
            "entity_1_id": r1["source_customer_id"],
            "entity_1_name": f"{r1.get('first_name', '')} {r1.get('last_name', '')}".strip(),
            "entity_1_email": r1.get("email", ""),
            "entity_1_phone": r1.get("phone", ""),
            "entity_2_source": r2["source_system"],
            "entity_2_id": r2["source_customer_id"],
            "entity_2_name": f"{r2.get('first_name', '')} {r2.get('last_name', '')}".strip(),
            "entity_2_email": r2.get("email", ""),
            "entity_2_phone": r2.get("phone", ""),
            "match_heuristic": heuristic,
            "similarity_score": round(similarity, 4),
            "review_status": "PENDING_REVIEW",
            "flagged_at": now_ts,
        })
