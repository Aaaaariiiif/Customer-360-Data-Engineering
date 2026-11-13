# Customer 360 Pipeline Reconciliation Report
**Run ID**: `RUN_20261113_094333_C4EAF7`  
**Overall Status**: **PASSED**  
**Checks Summary**: 10/10 Passed, 0 Failed, 0 Warnings

| Check Name | Status | Description | Details |
| :--- | :---: | :--- | :--- |
| Conservation of Customer Lineage | ✅ PASS | All valid customer records must be mapped 1:1 in bridge_customer_source_map | **valid_customers_ingested**: 56<br>**bridge_source_map_rows**: 56<br>**difference**: 0 |
| Volume Accounting: Customers | ✅ PASS | Input customers must account for valid, quarantined, or deduplicated rows | **input_rows**: 60<br>**valid_rows**: 56<br>**quarantined_rows**: 3<br>**accounted_rows**: 59<br>**in_batch_deduped**: 1 |
| Volume Accounting: Accounts | ✅ PASS | Input accounts must account for valid, quarantined, or deduplicated rows | **input_rows**: 75<br>**valid_rows**: 72<br>**quarantined_rows**: 3<br>**accounted_rows**: 75<br>**in_batch_deduped**: 0 |
| Volume Accounting: Orders | ✅ PASS | Input orders must account for valid, quarantined, or deduplicated rows | **input_rows**: 219<br>**valid_rows**: 216<br>**quarantined_rows**: 3<br>**accounted_rows**: 219<br>**in_batch_deduped**: 0 |
| Volume Accounting: Interactions | ✅ PASS | Input interactions must account for valid, quarantined, or deduplicated rows | **input_rows**: 116<br>**valid_rows**: 111<br>**quarantined_rows**: 5<br>**accounted_rows**: 116<br>**in_batch_deduped**: 0 |
| Referential Integrity in Unified Target Layer | ✅ PASS | Zero orphaned records in unified account, order, or interaction tables | **orphan_accounts**: 0<br>**orphan_orders**: 0<br>**orphan_interactions**: 0 |
| Financial Revenue Reconciliation | ✅ PASS | Completed order total amount must reconcile exactly with Customer 360 lifetime spend | **fct_order_completed_sum**: 141269.15<br>**customer_360_spend_sum**: 141269.15<br>**variance**: 0.0 |
| Target Primary Key Uniqueness | ✅ PASS | Zero duplicate unified_customer_id in golden customer dimension and 360 summary | **dim_unified_customer_duplicate_keys**: 0<br>**fact_customer_360_summary_duplicate_keys**: 0 |
| Uncertain Matches Isolation | ✅ PASS | Flagged uncertain pairs must remain isolated and NOT merged into the same golden ID | **total_uncertain_flagged**: 3<br>**improperly_merged_count**: 0 |
| Ground Truth Clustering Accuracy | ✅ PASS | Deterministic clusters match expected ground truth cluster labels | **total_ground_truth_clusters**: 52<br>**correctly_resolved_clusters**: 52<br>**accuracy_percentage**: 100.0% |