"""
Data Transformation and Customer 360 Feature Store Module.
Enriches and links accounts, orders, and interactions to unified customer entities,
and computes Customer 360 behavioral, financial, and engagement metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from src.schemas import (
    DIM_ACCOUNT_UNIFIED_COLUMNS,
    FCT_ORDER_UNIFIED_COLUMNS,
    FCT_INTERACTION_UNIFIED_COLUMNS,
    FACT_CUSTOMER_360_SUMMARY_COLUMNS,
)


class Customer360Transformer:
    """Transforms raw entities into unified dimensional and fact tables with 360 metrics."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.now_ts = datetime.now(timezone.utc).isoformat()

    def transform(
        self,
        clean_customers: pd.DataFrame,
        clean_accounts: pd.DataFrame,
        clean_orders: pd.DataFrame,
        clean_interactions: pd.DataFrame,
        dim_unified_customer: pd.DataFrame,
        bridge_customer_source_map: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Executes unified linking and metric rollups.
        Returns:
            - dim_account_unified
            - fct_order_unified
            - fct_interaction_unified
            - fact_customer_360_summary
        """
        # Build mapping: (source_system, source_customer_id) -> unified_customer_id
        # and fallback customer_id -> unified_customer_id
        cust_to_unified: Dict[Tuple[str, str], str] = {}
        fallback_cust_to_unified: Dict[str, str] = {}

        if not bridge_customer_source_map.empty:
            for _, r in bridge_customer_source_map.iterrows():
                u_id = str(r["unified_customer_id"])
                s_sys = str(r["source_system"])
                s_cid = str(r["source_customer_id"])
                cust_to_unified[(s_sys, s_cid)] = u_id
                fallback_cust_to_unified[s_cid] = u_id

        # -------------------------------------------------------------------
        # 1. Transform Accounts -> dim_account_unified
        # -------------------------------------------------------------------
        account_rows: List[Dict[str, Any]] = []
        account_to_unified: Dict[str, str] = {}

        if not clean_accounts.empty:
            for _, r in clean_accounts.iterrows():
                aid = str(r["account_id"])
                s_sys = str(r["source_system"])
                s_cid = str(r["source_customer_id"])

                u_id = cust_to_unified.get((s_sys, s_cid)) or fallback_cust_to_unified.get(s_cid, "UC_UNKNOWN")
                account_to_unified[aid] = u_id

                bal = r.get("balance", 0.0)
                try:
                    bal_val = float(bal)
                except (ValueError, TypeError):
                    bal_val = 0.0

                account_rows.append({
                    "account_id": aid,
                    "unified_customer_id": u_id,
                    "source_system": s_sys,
                    "source_customer_id": s_cid,
                    "account_number": str(r.get("account_number", "")),
                    "account_type": str(r.get("account_type", "")),
                    "status": str(r.get("status", "")),
                    "currency": str(r.get("currency", "USD")),
                    "balance": bal_val,
                    "opened_at": str(r.get("opened_at", "")),
                    "run_id": self.run_id,
                })

        dim_account_unified = pd.DataFrame(account_rows, columns=DIM_ACCOUNT_UNIFIED_COLUMNS)

        # -------------------------------------------------------------------
        # 2. Transform Orders -> fct_order_unified
        # -------------------------------------------------------------------
        order_rows: List[Dict[str, Any]] = []

        if not clean_orders.empty:
            for _, r in clean_orders.iterrows():
                oid = str(r["order_id"])
                aid = str(r["account_id"])
                s_sys = str(r["source_system"])
                s_cid = str(r.get("source_customer_id", ""))

                # Try resolving via account first, then direct customer link
                u_id = account_to_unified.get(aid)
                if not u_id or u_id == "UC_UNKNOWN":
                    u_id = cust_to_unified.get((s_sys, s_cid)) or fallback_cust_to_unified.get(s_cid, "UC_UNKNOWN")

                amt = r.get("total_amount", 0.0)
                try:
                    amt_val = float(amt)
                except (ValueError, TypeError):
                    amt_val = 0.0

                item_cnt = r.get("item_count", 1)
                try:
                    cnt_val = int(item_cnt)
                except (ValueError, TypeError):
                    cnt_val = 1

                order_rows.append({
                    "order_id": oid,
                    "unified_customer_id": u_id,
                    "account_id": aid,
                    "source_system": s_sys,
                    "order_timestamp": str(r.get("order_timestamp", "")),
                    "total_amount": amt_val,
                    "currency": str(r.get("currency", "USD")),
                    "status": str(r.get("status", "")),
                    "item_count": cnt_val,
                    "payment_method": str(r.get("payment_method", "")),
                    "run_id": self.run_id,
                })

        fct_order_unified = pd.DataFrame(order_rows, columns=FCT_ORDER_UNIFIED_COLUMNS)

        # -------------------------------------------------------------------
        # 3. Transform Interactions -> fct_interaction_unified
        # -------------------------------------------------------------------
        interaction_rows: List[Dict[str, Any]] = []

        if not clean_interactions.empty:
            for _, r in clean_interactions.iterrows():
                iid = str(r["interaction_id"])
                s_sys = str(r["source_system"])
                s_cid = str(r["source_customer_id"])
                aid = str(r.get("account_id", ""))

                u_id = cust_to_unified.get((s_sys, s_cid)) or fallback_cust_to_unified.get(s_cid)
                if not u_id and aid in account_to_unified:
                    u_id = account_to_unified[aid]
                if not u_id:
                    u_id = "UC_UNKNOWN"

                sent = r.get("sentiment_score", 0.0)
                try:
                    sent_val = float(sent)
                except (ValueError, TypeError):
                    sent_val = 0.0

                dur = r.get("duration_seconds", 0)
                try:
                    dur_val = int(dur)
                except (ValueError, TypeError):
                    dur_val = 0

                interaction_rows.append({
                    "interaction_id": iid,
                    "unified_customer_id": u_id,
                    "account_id": aid,
                    "source_system": s_sys,
                    "interaction_timestamp": str(r.get("interaction_timestamp", "")),
                    "channel": str(r.get("channel", "")),
                    "interaction_type": str(r.get("interaction_type", "")),
                    "sentiment_score": sent_val,
                    "resolution_status": str(r.get("resolution_status", "")),
                    "duration_seconds": dur_val,
                    "run_id": self.run_id,
                })

        fct_interaction_unified = pd.DataFrame(interaction_rows, columns=FCT_INTERACTION_UNIFIED_COLUMNS)

        # -------------------------------------------------------------------
        # 4. Generate Customer 360 Feature Store (fact_customer_360_summary)
        # -------------------------------------------------------------------
        summary_rows: List[Dict[str, Any]] = []

        # Index accounts by unified_customer_id
        acc_by_uc: Dict[str, List[Dict[str, Any]]] = {}
        for r in account_rows:
            acc_by_uc.setdefault(r["unified_customer_id"], []).append(r)

        # Index orders by unified_customer_id
        ord_by_uc: Dict[str, List[Dict[str, Any]]] = {}
        for r in order_rows:
            ord_by_uc.setdefault(r["unified_customer_id"], []).append(r)

        # Index interactions by unified_customer_id
        int_by_uc: Dict[str, List[Dict[str, Any]]] = {}
        for r in interaction_rows:
            int_by_uc.setdefault(r["unified_customer_id"], []).append(r)

        if not dim_unified_customer.empty:
            for _, r in dim_unified_customer.iterrows():
                uc_id = str(r["unified_customer_id"])

                # Account metrics
                user_accs = acc_by_uc.get(uc_id, [])
                total_accounts = len(user_accs)
                active_accounts = sum(1 for a in user_accs if a["status"].upper() == "ACTIVE")

                # Order metrics
                user_ords = ord_by_uc.get(uc_id, [])
                lifetime_order_count = len(user_ords)

                completed_ords = [o for o in user_ords if o["status"].upper() in ("COMPLETED", "DELIVERED")]
                completed_order_count = len(completed_ords)
                lifetime_spend_usd = round(sum(o["total_amount"] for o in completed_ords), 2)
                average_order_value_usd = (
                    round(lifetime_spend_usd / completed_order_count, 2)
                    if completed_order_count > 0
                    else 0.0
                )

                order_timestamps = [o["order_timestamp"] for o in user_ords if o.get("order_timestamp")]
                first_order_ts = min(order_timestamps) if order_timestamps else ""
                last_order_ts = max(order_timestamps) if order_timestamps else ""

                # Interaction metrics
                user_ints = int_by_uc.get(uc_id, [])
                total_interactions = len(user_ints)
                open_tickets = sum(
                    1
                    for i in user_ints
                    if i["resolution_status"].upper() in ("OPEN", "ESCALATED", "PENDING_USER")
                )
                sentiments = [i["sentiment_score"] for i in user_ints if i.get("sentiment_score") is not None]
                avg_sentiment = round(sum(sentiments) / len(sentiments), 2) if sentiments else 0.0

                int_timestamps = [i["interaction_timestamp"] for i in user_ints if i.get("interaction_timestamp")]
                last_int_ts = max(int_timestamps) if int_timestamps else ""

                # Customer Segmentation Logic
                if lifetime_spend_usd >= 1000.0 and completed_order_count >= 2:
                    segment = "VIP"
                elif lifetime_spend_usd >= 500.0:
                    segment = "HIGH_VALUE"
                elif open_tickets >= 2 or avg_sentiment < -0.2:
                    segment = "AT_RISK"
                elif completed_order_count >= 1:
                    segment = "REGULAR"
                else:
                    segment = "PROSPECT"

                summary_rows.append({
                    "unified_customer_id": uc_id,
                    "total_accounts": total_accounts,
                    "active_accounts": active_accounts,
                    "lifetime_order_count": lifetime_order_count,
                    "completed_order_count": completed_order_count,
                    "lifetime_spend_usd": lifetime_spend_usd,
                    "average_order_value_usd": average_order_value_usd,
                    "first_order_timestamp": first_order_ts,
                    "last_order_timestamp": last_order_ts,
                    "total_interactions": total_interactions,
                    "open_tickets_count": open_tickets,
                    "avg_sentiment_score": avg_sentiment,
                    "last_interaction_timestamp": last_int_ts,
                    "customer_segment": segment,
                    "last_computed_at": self.now_ts,
                    "run_id": self.run_id,
                })

        fact_customer_360_summary = pd.DataFrame(summary_rows, columns=FACT_CUSTOMER_360_SUMMARY_COLUMNS)

        return dim_account_unified, fct_order_unified, fct_interaction_unified, fact_customer_360_summary
