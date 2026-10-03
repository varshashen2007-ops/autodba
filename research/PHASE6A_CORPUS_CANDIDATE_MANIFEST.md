# Phase 6A: Corpus Candidate Manifest & Pre-Execution Audit

**Date:** 2026-10-01  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Baseline Directory:** `C:\Users\swarsh\Desktop\autodba-main` (110 files, pristine & untouched)  
**Status:** PRE-EXECUTION AUDIT ONLY (No database mutations, no index creations, no commits, no pushes)

---

## 1. Executive Summary & Audit Purpose

This manifest documents, audits, and validates all proposed experimental measurement cases prior to execution in Phase 6A.

### Core Objectives:
1. **Grounded Candidate Sets:** Ensure candidate sets are derived directly from the authoritative logic of `RecommendationEngine.extract_candidate_columns`, `PlanAnalyzer`, and `IntelligenceService._evaluate_candidates`, avoiding arbitrary or ungrounded candidate generation.
2. **Physical Index Collision Prevention:** Verify every proposed candidate index against PostgreSQL 17.11 physical catalog metadata (`pg_indexes`) to guarantee zero pre-flight collisions or duplicate physical index aborts.
3. **Discriminative Balance ($|C| \ge 2$ vs $|C|=1$):** Establish a balanced corpus containing both single-candidate control cases (for pipeline and repeatability validation) and multi-candidate discriminative cases (for policy divergence and outcome-aware ranking evaluation).
4. **Strict Leakage Boundaries:** Categorize cases into 8 distinct canonical templates ensuring that Train and Test partitions remain strictly disjoint under `canonicalize_sql()` hashing.

---

## 2. Physical Schema & Index Baseline Grounding

### 2.1 Live PostgreSQL 17.11 Physical Catalog State (`public` schema)
[CONFIRMED FROM CODE/SCHEMA]

| Table | Row Count | Existing Physical Indexes | Unindexed Attributes Available for Candidates |
| :--- | :--- | :--- | :--- |
| **`orders`** | 5,000 | `orders_pkey` (`id`), `idx_orders_order_date` (`order_date`) | `customer_id`, `total_amount`, `status`, `(customer_id, total_amount)`, `(customer_id, status)` |
| **`order_items`** | 15,000 | `order_items_pkey` (`id`), `idx_order_items_order_id` (`order_id`), `idx_order_items_product_id` (`product_id`) | `unit_price`, `quantity`, `(quantity, unit_price)` |
| **`customers`** | 500 | `customers_pkey` (`id`), `customers_email_key` (`email`) | `name`, `created_at` |
| **`products`** | 100 | `products_pkey` (`id`), `idx_products_category` (`category`) | *Excluded from index tuning (table too small)* |

### 2.2 Critical Schema Collision Adjustment
- **Finding:** In the initial experiment design, Template `T5` proposed `SELECT * FROM order_items WHERE product_id = ?;`.
- **Collision Risk:** `order_items` already possesses physical index `idx_order_items_product_id ON public.order_items USING btree (product_id)`. `MeasuredCaseRunner.find_equivalent_index` would detect this index during pre-flight and immediately abort execution.
- **Adjustment:** Template `T5` is adjusted to filter on `quantity > ?`, targeting the unindexed column `quantity`. This guarantees clean Sequential Scan baselines and eliminates pre-flight index collisions.

---

## 3. Candidate Generation Mechanics in AutoDBA

[CONFIRMED FROM CODE/SCHEMA]

In `IntelligenceService._evaluate_candidates` (lines 175–220) and `RecommendationEngine.extract_candidate_columns` (lines 81–120):
1. **Single-Predicate Queries** (e.g. `WHERE customer_id = 42`):
   - `extract_candidate_columns` extracts `['customer_id']`.
   - Candidate definitions generated: `[(['customer_id'], True), (['customer_id'], False)]`.
   - Deduplicated candidate pool size: **$|C| = 1$** (`cand_orders_customer_id`).
2. **Compound-Predicate Queries** (e.g. `WHERE customer_id = 42 AND total_amount > 100`):
   - `extract_candidate_columns` extracts `['customer_id', 'total_amount']`.
   - Candidate definitions generated:
     1. `(['customer_id', 'total_amount'], True)` $\rightarrow$ Composite baseline candidate
     2. `(['customer_id'], False)` $\rightarrow$ Single-column candidate 1
     3. `(['total_amount'], False)` $\rightarrow$ Single-column candidate 2
   - Deduplicated candidate pool size: **$|C| = 3$**.

---

## 4. Proposed Corpus Candidate Manifest (20 Cases / 8 Templates)

### Template T1: Orders Customer Lookup (Single Equality)
- **Canonical SQL:** `SELECT * FROM orders WHERE customer_id = ?;`
- **Target Table:** `orders` (5,000 rows)
- **Predicate Structure:** `customer_id = ?`
- **Expected Selectivity:** High ($\approx 0.2\%$, ~10 rows / 5,000)
- **Expected Candidates:** `cand_orders_customer_id` (`orders(customer_id)`)
- **Expected $|C|$:** **1**
- **Partition Role:** **TRAIN** (Control / Baseline speedup)
- **Physical Collision Check:** No existing index on `orders(customer_id)` [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameter | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T1-01`** | `SELECT * FROM orders WHERE customer_id = 42;` | `42` | `['customer_id']` | No ($|C|=1$) | TRAIN | Existing Pilot Memory ID 1 (`rem_a430d842de75`). Authoritative historical record. |
| **`CASE-T1-02`** | `SELECT * FROM orders WHERE customer_id = 105;` | `105` | `['customer_id']` | No ($|C|=1$) | TRAIN | Shares Template T1 hash. Must reside in TRAIN. |
| **`CASE-T1-03`** | `SELECT * FROM orders WHERE customer_id = 278;` | `278` | `['customer_id']` | No ($|C|=1$) | TRAIN | Shares Template T1 hash. Must reside in TRAIN. |

---

### Template T2: Orders Amount Filter (Single Range)
- **Canonical SQL:** `SELECT * FROM orders WHERE total_amount > ?;`
- **Target Table:** `orders` (5,000 rows)
- **Predicate Structure:** `total_amount > ?`
- **Expected Selectivity:** Medium ($\approx 5\text{--}10\%$, ~250–500 rows / 5,000)
- **Expected Candidates:** `cand_orders_total_amount` (`orders(total_amount)`)
- **Expected $|C|$:** **1**
- **Partition Role:** **TRAIN** (Moderate speedup / range scan)
- **Physical Collision Check:** No existing index on `orders(total_amount)` [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameter | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T2-01`** | `SELECT * FROM orders WHERE total_amount > 450.00;` | `450.00` | `['total_amount']` | No ($|C|=1$) | TRAIN | Distinct template from T1. Safe for TRAIN. |
| **`CASE-T2-02`** | `SELECT * FROM orders WHERE total_amount > 480.00;` | `480.00` | `['total_amount']` | No ($|C|=1$) | TRAIN | Shares Template T2 hash. Must reside in TRAIN. |
| **`CASE-T2-03`** | `SELECT * FROM orders WHERE total_amount > 420.00;` | `420.00` | `['total_amount']` | No ($|C|=1$) | TRAIN | Shares Template T2 hash. Must reside in TRAIN. |

---

### Template T3: Orders Customer & Amount Compound Filter
- **Canonical SQL:** `SELECT * FROM orders WHERE customer_id = ? AND total_amount > ?;`
- **Target Table:** `orders` (5,000 rows)
- **Predicate Structure:** `customer_id = ? AND total_amount > ?`
- **Expected Selectivity:** High ($\approx 0.04\%$, ~1–3 rows / 5,000)
- **Expected Candidates:**
  1. `cand_orders_customer_id_total_amount` (composite, baseline)
  2. `cand_orders_customer_id` (single-column)
  3. `cand_orders_total_amount` (single-column)
- **Expected $|C|$:** **3**
- **Partition Role:** **TRAIN** (Multi-candidate training ground)
- **Physical Collision Check:** Neither column is indexed physically [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameters | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T3-01`** | `SELECT * FROM orders WHERE customer_id = 42 AND total_amount > 100.00;` | `42`, `100.00` | `['customer_id', 'total_amount']`, `['customer_id']`, `['total_amount']` | **Yes ($|C|=3$)** | TRAIN | Core discriminative training case. |
| **`CASE-T3-02`** | `SELECT * FROM orders WHERE customer_id = 105 AND total_amount > 150.00;` | `105`, `150.00` | `['customer_id', 'total_amount']`, `['customer_id']`, `['total_amount']` | **Yes ($|C|=3$)** | TRAIN | Shares Template T3 hash. Must reside in TRAIN. |
| **`CASE-T3-03`** | `SELECT * FROM orders WHERE customer_id = 278 AND total_amount > 200.00;` | `278`, `200.00` | `['customer_id', 'total_amount']`, `['customer_id']`, `['total_amount']` | **Yes ($|C|=3$)** | TRAIN | Shares Template T3 hash. Must reside in TRAIN. |

---

### Template T4: Orders Status Filter (Low Selectivity / Regression Risk)
- **Canonical SQL:** `SELECT * FROM orders WHERE status = ?;`
- **Target Table:** `orders` (5,000 rows)
- **Predicate Structure:** `status = ?`
- **Expected Selectivity:** Low ($\approx 33\%$, ~1,666 rows / 5,000)
- **Expected Candidates:** `cand_orders_status` (`orders(status)`)
- **Expected $|C|$:** **1**
- **Partition Role:** **TRAIN** (Potential regression case for training $\lambda_{\text{reg}}$ penalty)
- **Physical Collision Check:** No existing index on `orders(status)` [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameter | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T4-01`** | `SELECT * FROM orders WHERE status = 'CANCELLED';` | `'CANCELLED'` | `['status']` | No ($|C|=1$) | TRAIN | Tests index scan vs seq scan behavior on low selectivity. |
| **`CASE-T4-02`** | `SELECT * FROM orders WHERE status = 'PENDING';` | `'PENDING'` | `['status']` | No ($|C|=1$) | TRAIN | Shares Template T4 hash. Must reside in TRAIN. |

---

### Template T5: Order Items Quantity Filter (Single Range)
- **Canonical SQL:** `SELECT * FROM order_items WHERE quantity > ?;`
- **Target Table:** `order_items` (15,000 rows)
- **Predicate Structure:** `quantity > ?`
- **Expected Selectivity:** Medium ($\approx 10\%$, ~1,500 rows / 15,000)
- **Expected Candidates:** `cand_order_items_quantity` (`order_items(quantity)`)
- **Expected $|C|$:** **1**
- **Partition Role:** **TRAIN** (Order items single-column baseline)
- **Physical Collision Check:** No existing index on `order_items(quantity)` [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameter | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T5-01`** | `SELECT * FROM order_items WHERE quantity > 8;` | `8` | `['quantity']` | No ($|C|=1$) | TRAIN | Replaces initial `product_id` proposal to prevent collision with `idx_order_items_product_id`. |
| **`CASE-T5-02`** | `SELECT * FROM order_items WHERE quantity > 9;` | `9` | `['quantity']` | No ($|C|=1$) | TRAIN | Shares Template T5 hash. Must reside in TRAIN. |

---

### Template T6: Order Items Unit Price Filter (Single Range)
- **Canonical SQL:** `SELECT * FROM order_items WHERE unit_price > ?;`
- **Target Table:** `order_items` (15,000 rows)
- **Predicate Structure:** `unit_price > ?`
- **Expected Selectivity:** Medium ($\approx 5\%$, ~750 rows / 15,000)
- **Expected Candidates:** `cand_order_items_unit_price` (`order_items(unit_price)`)
- **Expected $|C|$:** **1**
- **Partition Role:** **TRAIN** (Order items single-column baseline)
- **Physical Collision Check:** No existing index on `order_items(unit_price)` [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameter | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T6-01`** | `SELECT * FROM order_items WHERE unit_price > 95.00;` | `95.00` | `['unit_price']` | No ($|C|=1$) | TRAIN | Clean sequential scan baseline on 15k rows. |
| **`CASE-T6-02`** | `SELECT * FROM order_items WHERE unit_price > 90.00;` | `90.00` | `['unit_price']` | No ($|C|=1$) | TRAIN | Shares Template T6 hash. Must reside in TRAIN. |

---

### Template T7: Order Items Quantity & Unit Price Compound Filter (Multi-Candidate)
- **Canonical SQL:** `SELECT * FROM order_items WHERE quantity > ? AND unit_price > ?;`
- **Target Table:** `order_items` (15,000 rows)
- **Predicate Structure:** `quantity > ? AND unit_price > ?`
- **Expected Selectivity:** High ($\approx 0.5\%$, ~75 rows / 15,000)
- **Expected Candidates:**
  1. `cand_order_items_quantity_unit_price` (composite, baseline)
  2. `cand_order_items_quantity` (single-column)
  3. `cand_order_items_unit_price` (single-column)
- **Expected $|C|$:** **3**
- **Partition Role:** **TEST** (Unseen evaluation query template for A/B/C comparison)
- **Physical Collision Check:** Neither `quantity`, `unit_price`, nor `(quantity, unit_price)` is indexed [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameters | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T7-01`** | `SELECT * FROM order_items WHERE quantity > 7 AND unit_price > 80.00;` | `7`, `80.00` | `['quantity', 'unit_price']`, `['quantity']`, `['unit_price']` | **Yes ($|C|=3$)** | **TEST** | Primary multi-candidate evaluation case on `order_items`. |
| **`CASE-T7-02`** | `SELECT * FROM order_items WHERE quantity > 8 AND unit_price > 85.00;` | `8`, `85.00` | `['quantity', 'unit_price']`, `['quantity']`, `['unit_price']` | **Yes ($|C|=3$)** | **TEST** | Shares Template T7 hash. Must reside in TEST. |
| **`CASE-T7-03`** | `SELECT * FROM order_items WHERE quantity > 6 AND unit_price > 90.00;` | `6`, `90.00` | `['quantity', 'unit_price']`, `['quantity']`, `['unit_price']` | **Yes ($|C|=3$)** | **TEST** | Shares Template T7 hash. Must reside in TEST. |

---

### Template T8: Orders Customer & Status Compound Filter (Multi-Candidate)
- **Canonical SQL:** `SELECT * FROM orders WHERE customer_id = ? AND status = ?;`
- **Target Table:** `orders` (5,000 rows)
- **Predicate Structure:** `customer_id = ? AND status = ?`
- **Expected Selectivity:** High ($\approx 0.07\%$, ~3–4 rows / 5,000)
- **Expected Candidates:**
  1. `cand_orders_customer_id_status` (composite, baseline)
  2. `cand_orders_customer_id` (single-column)
  3. `cand_orders_status` (single-column)
- **Expected $|C|$:** **3**
- **Partition Role:** **TEST** (Unseen evaluation query template for A/B/C comparison)
- **Physical Collision Check:** Neither column is indexed physically [CONFIRMED FROM SCHEMA].

| Case ID | Concrete SQL Query | Parameters | Candidate Set | $|C| \ge 2$? | Role | Leakage / Exclusion Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T8-01`** | `SELECT * FROM orders WHERE customer_id = 42 AND status = 'COMPLETED';` | `42`, `'COMPLETED'` | `['customer_id', 'status']`, `['customer_id']`, `['status']` | **Yes ($|C|=3$)** | **TEST** | Primary multi-candidate evaluation case on `orders`. |
| **`CASE-T8-02`** | `SELECT * FROM orders WHERE customer_id = 105 AND status = 'SHIPPED';` | `105`, `'SHIPPED'` | `['customer_id', 'status']`, `['customer_id']`, `['status']` | **Yes ($|C|=3$)** | **TEST** | Shares Template T8 hash. Must reside in TEST. |

---

## 5. Summary Statistics & Partition Structure

### 5.1 Corpus Metrics Summary

| Metric | Target Value | Actual in Manifest | Status |
| :--- | :--- | :--- | :--- |
| **Total Proposed Cases ($M$)** | 12 to 20 | **20 cases** | ✅ Exact match (Target sizing achieved) |
| **Total Distinct Templates ($T$)** | 6 to 8 | **8 templates** | ✅ Exact match (8 distinct canonical shapes) |
| **Multi-Candidate Discriminative Cases ($|C| \ge 2$)** | $\ge 6$ | **8 cases** (T3: 3, T7: 3, T8: 2) | ✅ Excellent discriminative power ($40\%$) |
| **Single-Candidate Control Cases ($|C| = 1$)** | $\ge 6$ | **12 cases** (T1: 3, T2: 3, T4: 2, T5: 2, T6: 2) | ✅ Solid baseline & repeatability coverage ($60\%$) |
| **Target Relations Represented** | $\ge 2$ | `orders` (13 cases), `order_items` (7 cases) | ✅ Balanced across medium & large tables |

### 5.2 Grouped Template Train/Test Partition

```
TOTAL PROPOSED CORPUS (M = 20 cases, T = 8 templates)
│
├── TRAIN PARTITION (Frozen Historical Retrieval Memory)
│   ├── Template T1: orders (customer_id = ?)            [3 cases: CASE-T1-01 (Mem ID 1), CASE-T1-02, CASE-T1-03]
│   ├── Template T2: orders (total_amount > ?)           [3 cases: CASE-T2-01, CASE-T2-02, CASE-T2-03]
│   ├── Template T3: orders (customer_id + amount)       [3 cases: CASE-T3-01, CASE-T3-02, CASE-T3-03]  <-- |C|=3
│   ├── Template T4: orders (status = ?)                 [2 cases: CASE-T4-01, CASE-T4-02]              <-- Regression test
│   ├── Template T5: order_items (quantity > ?)          [2 cases: CASE-T5-01, CASE-T5-02]
│   └── Template T6: order_items (unit_price > ?)        [2 cases: CASE-T6-01, CASE-T6-02]
│   Total TRAIN: 6 Templates (75%), 15 Cases (75%)
│
└── TEST PARTITION (Held-Out Unseen Evaluation Queries)
    ├── Template T7: order_items (quantity + unit_price) [3 cases: CASE-T7-01, CASE-T7-02, CASE-T7-03]  <-- |C|=3
    └── Template T8: orders (customer_id + status)       [2 cases: CASE-T8-01, CASE-T8-02]              <-- |C|=3
    Total TEST: 2 Templates (25%), 5 Cases (25%)
```

---

## 6. Audit Classification & Readiness Verdict

### CONFIRMED FROM CODE/SCHEMA:
1. `RecommendationEngine.extract_candidate_columns` deterministically extracts candidate columns from filter clauses without hallucination.
2. `IntelligenceService._evaluate_candidates` generates composite baseline candidates and single-column sub-candidates for compound predicates, yielding $|C|=3$.
3. Single-predicate queries on unindexed columns yield $|C|=1$.
4. Target tables (`orders`, `order_items`) have zero conflicting physical indexes for all 20 proposed cases.
5. Historical pilot memory ID 1 (`CASE-T1-01`) is preserved and correctly anchored in Template `T1` (TRAIN partition).

### EXPECTED BUT REQUIRES RUNTIME VERIFICATION:
1. Runtime execution of `BottleneckDetector.detect()` on each individual query will be formally verified during runner execution to confirm `BottleneckType.MISSING_INDEX` is detected.
2. HypoPG simulated cost reduction and `SafetyAssessor` approval eligibility will be verified per candidate during execution.
3. Physical benchmark coefficient of variation ($\text{CoV} \le 0.50$) will be verified empirically on each run.

---

## 7. Readiness Verdict

# **A. MANIFEST AUDITED & READY FOR PHASE 6A EXECUTION**

The proposed 20-case / 8-template corpus is fully grounded in the existing code, schema, and safety constraints. All physical index collisions have been eliminated by design. Phase 6A execution can proceed safely using `MeasuredCaseRunner`.
