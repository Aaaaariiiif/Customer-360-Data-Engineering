"""
Reproducible Synthetic Dataset Generator.
Generates multi-source customer, account, order, and interaction datasets
with realistic anomalies, duplicates, edge cases, and ground-truth answer labels.
"""

from __future__ import annotations

import csv
import json
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Nancy", "Daniel", "Lisa",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
]

CITIES = [
    ("New York", "NY", "10001"),
    ("Los Angeles", "CA", "90001"),
    ("Chicago", "IL", "60601"),
    ("Houston", "TX", "77001"),
    ("Phoenix", "AZ", "85001"),
    ("Philadelphia", "PA", "19101"),
    ("San Antonio", "TX", "78201"),
    ("San Diego", "CA", "92101"),
    ("Dallas", "TX", "75201"),
    ("Austin", "TX", "78701"),
]

STREET_NAMES = [
    "Main St", "Oak Ave", "Maple Dr", "Pine St", "Cedar Ln",
    "Elm St", "Washington Blvd", "Lake Rd", "Park Ave", "Sunset Blvd"
]

SOURCE_SYSTEMS = ["CRM_NORTH_AMERICA", "CRM_EUROPE", "BILLING_CORE", "WEB_STORE"]


class DataGenerator:
    """Scalable, deterministic synthetic data generator."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def _random_date(self, start_year: int = 2020, end_year: int = 2025) -> str:
        start = datetime(start_year, 1, 1, tzinfo=timezone.utc)
        end = datetime(end_year, 12, 31, tzinfo=timezone.utc)
        delta = end - start
        random_seconds = self.rng.randint(0, int(delta.total_seconds()))
        dt = start + timedelta(seconds=random_seconds)
        return dt.isoformat()

    def generate(
        self,
        scale: str = "small",
        output_dir: str | Path = "data/sample",
        labels_dir: str | Path = "data/expected_labels",
    ) -> Dict[str, int]:
        """
        Generate datasets based on scale:
        - 'small': ~400 records across tables (includes targeted edge cases)
        - 'medium': ~50,000 records
        - 'large': ~200,000+ records (100k+ orders for stress testing)
        """
        out_path = Path(output_dir)
        labels_path = Path(labels_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        labels_path.mkdir(parents=True, exist_ok=True)

        if scale == "small":
            base_customers = 60
            account_multiplier = 1.3
            order_multiplier = 3.0
            interaction_multiplier = 2.0
        elif scale == "medium":
            base_customers = 5000
            account_multiplier = 1.6
            order_multiplier = 5.0
            interaction_multiplier = 3.0
        elif scale == "large":
            base_customers = 25000
            account_multiplier = 1.5
            order_multiplier = 4.5  # ~112,500 orders
            interaction_multiplier = 2.5
        else:
            raise ValueError(f"Unknown scale: {scale}. Choose 'small', 'medium', or 'large'.")

        customers: List[Dict[str, Any]] = []
        accounts: List[Dict[str, Any]] = []
        orders: List[Dict[str, Any]] = []
        interactions: List[Dict[str, Any]] = []
        expected_golden: List[Dict[str, Any]] = []

        # -------------------------------------------------------------------
        # 1. Deterministic Known Clusters & Edge Cases (in 'small' & base of all)
        # -------------------------------------------------------------------
        # Cluster 1: Exact Tax ID Match across CRM_NORTH_AMERICA & WEB_STORE
        cluster1_tax = "987-65-4321"
        c1_a = {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_CL1_A",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice.smith@example.com",
            "phone": "+1-555-0101",
            "address_line1": "100 Main St",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "tax_id": cluster1_tax,
            "date_of_birth": "1988-04-12",
            "source_created_at": "2021-01-15T09:00:00Z",
            "source_updated_at": "2023-05-10T14:30:00Z",
        }
        c1_b = {
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL1_B",
            "first_name": "Alice",
            "last_name": "Smith",
            "email": "alice.personal@gmail.com",  # different email, but same tax_id!
            "phone": "555-010-1000",
            "address_line1": "100 Main Street Apt 2",
            "city": "New York",
            "state": "NY",
            "postal_code": "10001",
            "country": "USA",
            "tax_id": cluster1_tax,
            "date_of_birth": "1988-04-12",
            "source_created_at": "2021-06-20T10:15:00Z",
            "source_updated_at": "2023-08-01T11:00:00Z",
        }
        customers.extend([c1_a, c1_b])
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_ALICE_SMITH",
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_CL1_A",
            "match_rule": "RULE_EXACT_TAX_ID",
            "is_uncertain": False,
        })
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_ALICE_SMITH",
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL1_B",
            "match_rule": "RULE_EXACT_TAX_ID",
            "is_uncertain": False,
        })

        # Cluster 2: Exact Email Match across CRM_EUROPE and BILLING_CORE
        cluster2_email = "robert.johnson@corporate.org"
        c2_a = {
            "source_system": "CRM_EUROPE",
            "source_customer_id": "CUST_CL2_A",
            "first_name": "Robert",
            "last_name": "Johnson",
            "email": cluster2_email,
            "phone": "+44-20-7946-0919",
            "address_line1": "221B Baker St",
            "city": "London",
            "state": "LDN",
            "postal_code": "NW16XE",
            "country": "GBR",
            "tax_id": "",
            "date_of_birth": "1975-11-23",
            "source_created_at": "2020-03-10T08:00:00Z",
            "source_updated_at": "2022-01-14T16:20:00Z",
        }
        c2_b = {
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_CL2_B",
            "first_name": "Bob",
            "last_name": "Johnson",
            "email": "ROBERT.JOHNSON@CORPORATE.ORG",  # Case difference, normalized email match!
            "phone": "",
            "address_line1": "221B Baker Street",
            "city": "London",
            "state": "LDN",
            "postal_code": "NW16XE",
            "country": "GBR",
            "tax_id": "",
            "date_of_birth": "1975-11-23",
            "source_created_at": "2020-04-01T12:00:00Z",
            "source_updated_at": "2023-11-05T09:45:00Z",
        }
        customers.extend([c2_a, c2_b])
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_BOB_JOHNSON",
            "source_system": "CRM_EUROPE",
            "source_customer_id": "CUST_CL2_A",
            "match_rule": "RULE_EXACT_EMAIL",
            "is_uncertain": False,
        })
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_BOB_JOHNSON",
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_CL2_B",
            "match_rule": "RULE_EXACT_EMAIL",
            "is_uncertain": False,
        })

        # Cluster 3: Exact Phone + Last Name Match
        c3_a = {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_CL3_A",
            "first_name": "Carol",
            "last_name": "Williams",
            "email": "carol.williams.work@corp.com",
            "phone": "(415) 555-2671",
            "address_line1": "456 Market St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94105",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1992-07-30",
            "source_created_at": "2022-02-15T10:00:00Z",
            "source_updated_at": "2023-01-20T12:00:00Z",
        }
        c3_b = {
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL3_B",
            "first_name": "Caroline",
            "last_name": "Williams",
            "email": "caroline92@gmail.com",
            "phone": "4155552671",  # Same phone stripped of formatting, same last name
            "address_line1": "789 Mission St",
            "city": "San Francisco",
            "state": "CA",
            "postal_code": "94103",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1992-07-30",
            "source_created_at": "2022-05-10T14:00:00Z",
            "source_updated_at": "2023-06-18T15:30:00Z",
        }
        customers.extend([c3_a, c3_b])
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_CAROL_WILLIAMS",
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_CL3_A",
            "match_rule": "RULE_EXACT_PHONE_AND_LAST_NAME",
            "is_uncertain": False,
        })
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_CAROL_WILLIAMS",
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL3_B",
            "match_rule": "RULE_EXACT_PHONE_AND_LAST_NAME",
            "is_uncertain": False,
        })

        # Cluster 4: Exact Name + Address Match
        c4_a = {
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_CL4_A",
            "first_name": "David",
            "last_name": "Brown",
            "email": "dbrown_old@isp.net",
            "phone": "212-555-8899",
            "address_line1": "742 Evergreen Terrace",
            "city": "Springfield",
            "state": "OR",
            "postal_code": "97477",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1980-09-15",
            "source_created_at": "2020-01-10T11:00:00Z",
            "source_updated_at": "2021-04-12T09:00:00Z",
        }
        c4_b = {
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL4_B",
            "first_name": "David",
            "last_name": "Brown",
            "email": "david.brown.new@tech.io",
            "phone": "503-555-1122",
            "address_line1": "742 evergreen terrace",
            "city": "Springfield",
            "state": "OR",
            "postal_code": "97477",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1980-09-15",
            "source_created_at": "2022-08-01T13:00:00Z",
            "source_updated_at": "2023-09-14T10:00:00Z",
        }
        customers.extend([c4_a, c4_b])
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_DAVID_BROWN",
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_CL4_A",
            "match_rule": "RULE_EXACT_NAME_AND_ADDRESS",
            "is_uncertain": False,
        })
        expected_golden.append({
            "expected_cluster_label": "CLUSTER_DAVID_BROWN",
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_CL4_B",
            "match_rule": "RULE_EXACT_NAME_AND_ADDRESS",
            "is_uncertain": False,
        })

        # -------------------------------------------------------------------
        # 2. Uncertain Matches (Must be flagged for review, NOT merged)
        # -------------------------------------------------------------------
        # Edge Case A: Shared Phone Number, Different Last Name (Roommates/Family landline)
        shared_phone = "312-555-9000"
        c_unc_1 = {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_UNC_PHONE_1",
            "first_name": "Emily",
            "last_name": "Clark",
            "email": "emily.clark@domain.org",
            "phone": shared_phone,
            "address_line1": "500 Michigan Ave",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60611",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1995-02-14",
            "source_created_at": "2022-01-10T10:00:00Z",
            "source_updated_at": "2023-01-10T10:00:00Z",
        }
        c_unc_2 = {
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_UNC_PHONE_2",
            "first_name": "Marcus",
            "last_name": "Vance",  # Different last name!
            "email": "mvance95@gmail.com",
            "phone": shared_phone,
            "address_line1": "500 Michigan Ave Apt 4B",
            "city": "Chicago",
            "state": "IL",
            "postal_code": "60611",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1994-08-20",
            "source_created_at": "2022-03-15T11:00:00Z",
            "source_updated_at": "2023-02-20T11:00:00Z",
        }
        customers.extend([c_unc_1, c_unc_2])
        expected_golden.append({
            "expected_cluster_label": "SINGLETON_EMILY_CLARK",
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_UNC_PHONE_1",
            "match_rule": "SINGLETON",
            "is_uncertain": True,
        })
        expected_golden.append({
            "expected_cluster_label": "SINGLETON_MARCUS_VANCE",
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_UNC_PHONE_2",
            "match_rule": "SINGLETON",
            "is_uncertain": True,
        })

        # Edge Case B: Same Address, Same Last Name, Different First Name (Parent & Child / Siblings)
        c_unc_3 = {
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_UNC_FAM_1",
            "first_name": "Thomas",
            "last_name": "Miller",
            "email": "thomas.miller.senior@household.com",
            "phone": "602-555-3344",
            "address_line1": "123 Desert Ridge Rd",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85001",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1960-05-15",
            "source_created_at": "2021-04-10T10:00:00Z",
            "source_updated_at": "2022-04-10T10:00:00Z",
        }
        c_unc_4 = {
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_UNC_FAM_2",
            "first_name": "Timothy",  # Different first name!
            "last_name": "Miller",
            "email": "tim.miller.jr@household.com",
            "phone": "602-555-7788",
            "address_line1": "123 Desert Ridge Rd",
            "city": "Phoenix",
            "state": "AZ",
            "postal_code": "85001",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1998-10-12",
            "source_created_at": "2022-09-01T10:00:00Z",
            "source_updated_at": "2023-03-12T10:00:00Z",
        }
        customers.extend([c_unc_3, c_unc_4])
        expected_golden.append({
            "expected_cluster_label": "SINGLETON_THOMAS_MILLER",
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_UNC_FAM_1",
            "match_rule": "SINGLETON",
            "is_uncertain": True,
        })
        expected_golden.append({
            "expected_cluster_label": "SINGLETON_TIMOTHY_MILLER",
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_UNC_FAM_2",
            "match_rule": "SINGLETON",
            "is_uncertain": True,
        })

        # -------------------------------------------------------------------
        # 3. Deliberately Malformed / Invalid Customer Records (Quarantine test)
        # -------------------------------------------------------------------
        # Malformed 1: Missing Mandatory First Name
        customers.append({
            "source_system": "CRM_NORTH_AMERICA",
            "source_customer_id": "CUST_BAD_NONAME",
            "first_name": "",  # MISSING REQUIRED FIELD!
            "last_name": "Mystery",
            "email": "mystery@example.com",
            "phone": "555-123-4567",
            "address_line1": "1 Mystery Ln",
            "city": "Denver",
            "state": "CO",
            "postal_code": "80201",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1990-01-01",
            "source_created_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        })
        # Malformed 2: Invalid Email Syntax
        customers.append({
            "source_system": "WEB_STORE",
            "source_customer_id": "CUST_BAD_EMAIL",
            "first_name": "Bad",
            "last_name": "Emailer",
            "email": "not-an-email-at-all",  # MALFORMED EMAIL!
            "phone": "555-987-6543",
            "address_line1": "2 Junk Rd",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1991-02-02",
            "source_created_at": "2022-02-02T00:00:00Z",
            "source_updated_at": "2022-02-02T00:00:00Z",
        })
        # Malformed 3: No Contact Details whatsoever (null email, phone, tax_id)
        customers.append({
            "source_system": "BILLING_CORE",
            "source_customer_id": "CUST_BAD_NOCONTACT",
            "first_name": "Ghost",
            "last_name": "User",
            "email": "",
            "phone": "",
            "address_line1": "3 Empty St",
            "city": "Seattle",
            "state": "WA",
            "postal_code": "98101",
            "country": "USA",
            "tax_id": "",
            "date_of_birth": "1985-03-03",
            "source_created_at": "2022-03-03T00:00:00Z",
            "source_updated_at": "2022-03-03T00:00:00Z",
        })

        # -------------------------------------------------------------------
        # 4. In-Batch Duplicate Customer Key (Idempotency / Deduplication test)
        # -------------------------------------------------------------------
        # Exact duplicate of CUST_CL1_A
        customers.append(dict(c1_a))

        # -------------------------------------------------------------------
        # 5. Populate Remaining Customers (Normal Singletons)
        # -------------------------------------------------------------------
        current_cust_count = len(customers)
        for i in range(current_cust_count, base_customers):
            fn = self.rng.choice(FIRST_NAMES)
            ln = self.rng.choice(LAST_NAMES)
            city, st, zip_code = self.rng.choice(CITIES)
            street = f"{self.rng.randint(100, 9999)} {self.rng.choice(STREET_NAMES)}"
            src_sys = self.rng.choice(SOURCE_SYSTEMS)
            cid = f"CUST_{src_sys[:3]}_{i:06d}"
            email = f"{fn.lower()}.{ln.lower()}{i}@{src_sys.lower().replace('_', '')}.com"
            phone = f"{self.rng.randint(200, 999)}-555-{self.rng.randint(1000, 9999)}"
            tax_id = f"{self.rng.randint(100, 999)}-{self.rng.randint(10, 99)}-{self.rng.randint(1000, 9999)}" if self.rng.random() < 0.4 else ""
            dob = f"{self.rng.randint(1960, 2004)}-{self.rng.randint(1, 12):02d}-{self.rng.randint(1, 28):02d}"
            c_at = self._random_date(2020, 2022)
            u_at = self._random_date(2023, 2024)

            customers.append({
                "source_system": src_sys,
                "source_customer_id": cid,
                "first_name": fn,
                "last_name": ln,
                "email": email,
                "phone": phone,
                "address_line1": street,
                "city": city,
                "state": st,
                "postal_code": zip_code,
                "country": "USA",
                "tax_id": tax_id,
                "date_of_birth": dob,
                "source_created_at": c_at,
                "source_updated_at": u_at,
            })
            expected_golden.append({
                "expected_cluster_label": f"SINGLETON_{cid}",
                "source_system": src_sys,
                "source_customer_id": cid,
                "match_rule": "SINGLETON",
                "is_uncertain": False,
            })

        # -------------------------------------------------------------------
        # 6. Accounts Generation & Referential Integrity
        # -------------------------------------------------------------------
        # Ensure our known clusters have accounts
        valid_cids = [c["source_customer_id"] for c in customers if c.get("first_name") and c.get("email")]

        # Cluster 1 accounts
        accounts.append({
            "source_system": "CRM_NORTH_AMERICA",
            "account_id": "ACC_CL1_01",
            "source_customer_id": "CUST_CL1_A",
            "account_number": "ACT-NA-1001",
            "account_type": "ENTERPRISE",
            "status": "ACTIVE",
            "currency": "USD",
            "balance": 15420.50,
            "opened_at": "2021-01-20T10:00:00Z",
            "source_updated_at": "2023-01-01T00:00:00Z",
        })
        accounts.append({
            "source_system": "WEB_STORE",
            "account_id": "ACC_CL1_02",
            "source_customer_id": "CUST_CL1_B",
            "account_number": "ACT-WS-5002",
            "account_type": "RETAIL",
            "status": "ACTIVE",
            "currency": "USD",
            "balance": 250.00,
            "opened_at": "2021-06-25T11:00:00Z",
            "source_updated_at": "2023-01-01T00:00:00Z",
        })

        # Deliberate Malformed Account: Missing Account Type
        accounts.append({
            "source_system": "BILLING_CORE",
            "account_id": "ACC_BAD_NOTYPE",
            "source_customer_id": "CUST_CL1_A",
            "account_number": "ACT-BAD-001",
            "account_type": "",  # MISSING REQUIRED!
            "status": "ACTIVE",
            "currency": "USD",
            "balance": 0.0,
            "opened_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        })

        # Deliberate Orphan Account: Invalid Parent Customer
        accounts.append({
            "source_system": "BILLING_CORE",
            "account_id": "ACC_ORPHAN_999",
            "source_customer_id": "NON_EXISTENT_CUSTOMER_XYZ",  # REFERENTIAL INTEGRITY VIOLATION!
            "account_number": "ACT-ORPHAN-999",
            "account_type": "CHECKING",
            "status": "ACTIVE",
            "currency": "USD",
            "balance": 500.0,
            "opened_at": "2022-01-01T00:00:00Z",
            "source_updated_at": "2022-01-01T00:00:00Z",
        })

        # Populate remaining accounts
        total_accounts_target = int(len(valid_cids) * account_multiplier)
        for i in range(len(accounts), total_accounts_target):
            parent_cid = self.rng.choice(valid_cids)
            acc_type = self.rng.choice(["CHECKING", "SAVINGS", "CREDIT", "ENTERPRISE", "RETAIL"])
            status = self.rng.choice(["ACTIVE", "ACTIVE", "ACTIVE", "SUSPENDED", "CLOSED"])
            bal = round(self.rng.uniform(10.0, 50000.0), 2)
            opened = self._random_date(2021, 2023)
            accounts.append({
                "source_system": "BILLING_CORE",
                "account_id": f"ACC_{i:06d}",
                "source_customer_id": parent_cid,
                "account_number": f"ACT-{i:07d}",
                "account_type": acc_type,
                "status": status,
                "currency": "USD",
                "balance": bal,
                "opened_at": opened,
                "source_updated_at": opened,
            })

        valid_account_ids = [a["account_id"] for a in accounts if a["account_id"] not in ("ACC_BAD_NOTYPE", "ACC_ORPHAN_999")]

        # -------------------------------------------------------------------
        # 7. Orders Generation
        # -------------------------------------------------------------------
        # Cluster 1 Known Orders
        orders.append({
            "source_system": "CRM_NORTH_AMERICA",
            "order_id": "ORD_CL1_001",
            "account_id": "ACC_CL1_01",
            "source_customer_id": "CUST_CL1_A",
            "order_timestamp": "2022-03-15T14:20:00Z",
            "total_amount": 1250.00,
            "currency": "USD",
            "status": "COMPLETED",
            "item_count": 3,
            "payment_method": "BANK_TRANSFER",
            "source_updated_at": "2022-03-15T15:00:00Z",
        })
        orders.append({
            "source_system": "WEB_STORE",
            "order_id": "ORD_CL1_002",
            "account_id": "ACC_CL1_02",
            "source_customer_id": "CUST_CL1_B",
            "order_timestamp": "2023-07-22T09:10:00Z",
            "total_amount": 180.50,
            "currency": "USD",
            "status": "COMPLETED",
            "item_count": 1,
            "payment_method": "CREDIT_CARD",
            "source_updated_at": "2023-07-22T09:15:00Z",
        })
        # Order with Negative Amount (Refund / Return) -> domain edge case
        orders.append({
            "source_system": "WEB_STORE",
            "order_id": "ORD_CL1_003_REFUND",
            "account_id": "ACC_CL1_02",
            "source_customer_id": "CUST_CL1_B",
            "order_timestamp": "2023-08-01T16:00:00Z",
            "total_amount": -50.00,  # Negative refund record
            "currency": "USD",
            "status": "REFUNDED",
            "item_count": 1,
            "payment_method": "CREDIT_CARD",
            "source_updated_at": "2023-08-01T16:00:00Z",
        })

        # Deliberate Malformed Order: Invalid Timestamp
        orders.append({
            "source_system": "WEB_STORE",
            "order_id": "ORD_BAD_TIME",
            "account_id": "ACC_CL1_01",
            "source_customer_id": "CUST_CL1_A",
            "order_timestamp": "NOT_A_TIMESTAMP",  # MALFORMED!
            "total_amount": 100.00,
            "currency": "USD",
            "status": "COMPLETED",
            "item_count": 1,
            "payment_method": "CREDIT_CARD",
            "source_updated_at": "2023-01-01T00:00:00Z",
        })

        # Deliberate Orphan Order: Non-existent Account
        orders.append({
            "source_system": "WEB_STORE",
            "order_id": "ORD_ORPHAN_ACC",
            "account_id": "ACC_DOES_NOT_EXIST_999",  # REFERENTIAL INTEGRITY VIOLATION!
            "source_customer_id": "CUST_CL1_A",
            "order_timestamp": "2023-01-01T10:00:00Z",
            "total_amount": 250.00,
            "currency": "USD",
            "status": "COMPLETED",
            "item_count": 2,
            "payment_method": "CREDIT_CARD",
            "source_updated_at": "2023-01-01T10:00:00Z",
        })

        # Populate remaining orders
        total_orders_target = int(len(valid_account_ids) * order_multiplier)
        for i in range(len(orders), total_orders_target):
            parent_acc = self.rng.choice(valid_account_ids)
            amt = round(self.rng.uniform(15.0, 2500.0), 2)
            st = self.rng.choice(["COMPLETED", "COMPLETED", "COMPLETED", "PENDING", "CANCELLED"])
            ots = self._random_date(2022, 2024)
            items = self.rng.randint(1, 10)
            pm = self.rng.choice(["CREDIT_CARD", "PAYPAL", "BANK_TRANSFER", "CRYPTO"])
            orders.append({
                "source_system": "WEB_STORE",
                "order_id": f"ORD_{i:07d}",
                "account_id": parent_acc,
                "source_customer_id": "",
                "order_timestamp": ots,
                "total_amount": amt,
                "currency": "USD",
                "status": st,
                "item_count": items,
                "payment_method": pm,
                "source_updated_at": ots,
            })

        # -------------------------------------------------------------------
        # 8. Interactions Generation
        # -------------------------------------------------------------------
        # Cluster 1 Interaction
        interactions.append({
            "source_system": "CRM_NORTH_AMERICA",
            "interaction_id": "INT_CL1_001",
            "source_customer_id": "CUST_CL1_A",
            "account_id": "ACC_CL1_01",
            "interaction_timestamp": "2023-02-10T11:15:00Z",
            "channel": "PHONE",
            "interaction_type": "INQUIRY",
            "sentiment_score": 0.85,
            "resolution_status": "RESOLVED",
            "duration_seconds": 320,
            "notes": "Customer asked about VIP reward program",
        })
        interactions.append({
            "source_system": "WEB_STORE",
            "interaction_id": "INT_CL1_002",
            "source_customer_id": "CUST_CL1_B",
            "account_id": "ACC_CL1_02",
            "interaction_timestamp": "2023-08-02T10:00:00Z",
            "channel": "CHAT",
            "interaction_type": "COMPLAINT",
            "sentiment_score": -0.60,
            "resolution_status": "RESOLVED",
            "duration_seconds": 450,
            "notes": "Discussed refund for order ORD_CL1_003_REFUND",
        })

        # Deliberate Malformed Interaction: Sentiment score out of [-1.0, 1.0] bounds
        interactions.append({
            "source_system": "CRM_NORTH_AMERICA",
            "interaction_id": "INT_BAD_SENTIMENT",
            "source_customer_id": "CUST_CL1_A",
            "account_id": "ACC_CL1_01",
            "interaction_timestamp": "2023-01-01T00:00:00Z",
            "channel": "CHAT",
            "interaction_type": "INQUIRY",
            "sentiment_score": 999.0,  # OUT OF BOUNDS!
            "resolution_status": "RESOLVED",
            "duration_seconds": 60,
            "notes": "Invalid sentiment score",
        })

        # Deliberate Orphan Interaction: Customer does not exist
        interactions.append({
            "source_system": "CRM_NORTH_AMERICA",
            "interaction_id": "INT_ORPHAN_CUST",
            "source_customer_id": "NON_EXISTENT_CUST_777",  # REFERENTIAL INTEGRITY VIOLATION!
            "account_id": "",
            "interaction_timestamp": "2023-01-01T00:00:00Z",
            "channel": "EMAIL",
            "interaction_type": "INQUIRY",
            "sentiment_score": 0.0,
            "resolution_status": "OPEN",
            "duration_seconds": 0,
            "notes": "Orphan interaction",
        })

        # Populate remaining interactions
        total_interactions_target = int(len(valid_cids) * interaction_multiplier)
        for i in range(len(interactions), total_interactions_target):
            parent_cid = self.rng.choice(valid_cids)
            ch = self.rng.choice(["CHAT", "EMAIL", "PHONE", "PORTAL"])
            itype = self.rng.choice(["INQUIRY", "COMPLAINT", "TECHNICAL_SUPPORT", "BILLING", "FEEDBACK"])
            sent = round(self.rng.uniform(-1.0, 1.0), 2)
            res = self.rng.choice(["RESOLVED", "RESOLVED", "OPEN", "ESCALATED"])
            dur = self.rng.randint(30, 1800)
            its = self._random_date(2022, 2024)
            interactions.append({
                "source_system": "SUPPORT_DESK",
                "interaction_id": f"INT_{i:07d}",
                "source_customer_id": parent_cid,
                "account_id": "",
                "interaction_timestamp": its,
                "channel": ch,
                "interaction_type": itype,
                "sentiment_score": sent,
                "resolution_status": res,
                "duration_seconds": dur,
                "notes": f"Standard support ticket {i}",
            })

        # -------------------------------------------------------------------
        # 9. Write CSV Files to Output Directory
        # -------------------------------------------------------------------
        def _write_csv(file_path: Path, rows: List[Dict[str, Any]]):
            if not rows:
                return
            headers = list(rows[0].keys())
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)

        _write_csv(out_path / "customers.csv", customers)
        _write_csv(out_path / "accounts.csv", accounts)
        _write_csv(out_path / "orders.csv", orders)
        _write_csv(out_path / "interactions.csv", interactions)

        # Write Ground Truth Labels separately
        _write_csv(labels_path / "expected_golden_customers.csv", expected_golden)

        counts = {
            "customers": len(customers),
            "accounts": len(accounts),
            "orders": len(orders),
            "interactions": len(interactions),
            "expected_labels": len(expected_golden),
        }
        return counts
