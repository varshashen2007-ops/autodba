# Phase 6C: Leakage-Controlled Split & Partition Lock

**Date:** 2026-10-01  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Manifest File:** `research/phase6c_partition_manifest.json`  
**Manifest SHA-256:** `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`  
**Baseline Directory:** `C:\Users\swarsh\Desktop\autodba-main` (110 files, pristine & untouched)  
**Status:** FROZEN & LOCKED FOR EVALUATION (No database mutations, no code changes, no commits)

---

## 1. Source Corpus Specification

The evaluation corpus consists strictly of the **14 validated measured cases** verified in Phase 6B:
- **Total Valid Measured Cases:** 14 (Memory IDs 1 through 14)
- **Data Provenance:** 100% `provenance == "measured"`, `is_verified == True`, `verification_state == "verified_measured"`.
- **Exclusions:** Zero synthetic, seeded, unverified, or failed cases are included.
- **Pilot Memory ID 1:** Preserved as Case 1 (`CASE-T1-01`).

---

## 2. Canonical Template Grouping & Template Hashes

Grouped template splitting is grounded strictly in deterministic canonicalization via `research.case_schema.canonicalize_sql()`. The fundamental unit of leakage control is the canonical SQL template:

| Template ID | Canonical SQL Template | SHA-256 Template Hash | Partition | Memory IDs | Case Count |
| :---: | :--- | :--- | :---: | :---: | :---: |
| **`T1`** | `select * from orders where customer_id = ?` | `036cb1ede04b97e1c6f74baa1d4fdce5cbfb6cca2ad7c64a8018d1c4f608a636` | **TRAIN** | 1, 2, 3 | 3 |
| **`T2`** | `select * from orders where total_amount > ?` | `f5bbbbeea30650c2c997aeadc2230f1b37fe979559019aba0304bf15730e563c` | **TRAIN** | 4, 5, 6 | 3 |
| **`T3`** | `select * from orders where customer_id = ? and total_amount > ?` | `30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2` | **DEV** | 7 | 1 |
| **`T5`** | `select * from order_items where quantity > ?` | `ec86cb8a6a578331cf91ef035d55eecf792b513bc1d8a4369e59d997cf2961e6` | **DEV** | 8, 9 | 2 |
| **`T7`** | `select * from order_items where quantity > ? and unit_price > ?` | `a329be083dbb562095cc1a836da106ae7752b04c8f58359bfa35165c3258fa72` | **TEST** | 10, 11, 12 | 3 |
| **`T8`** | `select * from orders where customer_id = ? and status = ?` | `1e0284488b0a996cbbfa7a4ecb819f39aa111b7d56ae18413b5ef2d0013f70aa` | **TEST** | 13, 14 | 2 |

---

## 3. Partition Design & Sizing Rationale

```
TOTAL MEASURED CORPUS (M = 14 cases, T = 6 templates)
│
├── TRAIN PARTITION (Frozen Historical Retrieval Corpus)
│   ├── Template T1: orders(customer_id = ?)            [3 cases: IDs 1, 2, 3]
│   └── Template T2: orders(total_amount > ?)           [3 cases: IDs 4, 5, 6]
│   Total TRAIN: 2 Templates (33.3%), 6 Cases (42.9%)
│
├── DEV PARTITION (Hyperparameter Selection & Validation)
│   ├── Template T3: orders(customer_id + amount)       [1 case: ID 7]   <-- Multi-candidate (|C|=3)
│   └── Template T5: order_items(quantity > ?)          [2 cases: IDs 8, 9]
│   Total DEV: 2 Templates (33.3%), 3 Cases (21.4%)
│
└── TEST PARTITION (Held-Out Unseen Evaluation Queries)
    ├── Template T7: order_items(quantity + unit_price) [3 cases: IDs 10, 11, 12] <-- Multi-candidate (|C|=3)
    └── Template T8: orders(customer_id + status)       [2 cases: IDs 13, 14]     <-- Compound query
    Total TEST: 2 Templates (33.3%), 5 Cases (35.7%)
```

### Rationale for TRAIN / DEV Division:
1. **TRAIN (`T1`, `T2`):** Supplies clean, single-predicate historical baselines on `orders` covering both equality lookup (`customer_id`) and range scan (`total_amount`).
2. **DEV (`T3`, `T5`):** Serves as a small development set to evaluate hyperparameter sensitivity ($\alpha, \beta, \lambda_{\text{reg}}$). `T3` contains candidates matching TRAIN `T1` (`customer_id`) and `T2` (`total_amount`), enabling parameter verification without exposing TEST.
3. **TEST (`T7`, `T8`):** Remains strictly held out. `T7` on `order_items` tests unseen multi-candidate selection ($|C|=3$) on a completely different table. `T8` tests compound equality/status predicates on `orders`.

---

## 4. Formal Partition & Leakage Invariants

All partition invariants have been mathematically and programmatically verified:

| Invariant | Formal Definition | Verification Result |
| :--- | :--- | :--- |
| **Zero Template Overlap (Train/Dev)** | $\text{Templates}(\text{TRAIN}) \cap \text{Templates}(\text{DEV}) = \emptyset$ | ✅ **Verified** (`{T1, T2} ∩ {T3, T5} = ∅`) |
| **Zero Template Overlap (Train/Test)** | $\text{Templates}(\text{TRAIN}) \cap \text{Templates}(\text{TEST}) = \emptyset$ | ✅ **Verified** (`{T1, T2} ∩ {T7, T8} = ∅`) |
| **Zero Template Overlap (Dev/Test)** | $\text{Templates}(\text{DEV}) \cap \text{Templates}(\text{TEST}) = \emptyset$ | ✅ **Verified** (`{T3, T5} ∩ {T7, T8} = ∅`) |
| **Zero Case ID Overlap** | $\text{Cases}(\text{TRAIN}) \cap \text{Cases}(\text{DEV}) \cap \text{Cases}(\text{TEST}) = \emptyset$ | ✅ **Verified** (`{1..6} ∩ {7..9} ∩ {10..14} = ∅`) |
| **Partition Completeness** | $|\text{TRAIN}| + |\text{DEV}| + |\text{TEST}| = 6 + 3 + 5 = 14$ | ✅ **Verified** (100% of corpus assigned) |

---

## 5. Retrieval Corpus Rule & Information Flow Boundary

To prevent evaluation leakage and forward contamination during Phase 6D:
1. **Retrieval Memory Boundary:** Policy B (Similarity) and Policy C (Outcome-Aware) can retrieve historical cases **strictly from the TRAIN partition** (Memory IDs 1, 2, 3, 4, 5, 6).
2. **DEV / TEST Isolation:** DEV cases (IDs 7, 8, 9) and TEST cases (IDs 10, 11, 12, 13, 14) are **never loaded into the historical memory index** during policy candidate ranking.
3. **Evaluation Immutability:** Benchmark timings measured during test candidate execution are recorded solely in experiment result logs and are never persisted into the live retrieval memory table during the experiment.

---

## 6. Hyperparameter Tuning Protocol & Boundaries

### Hyperparameter Scope:
- $\alpha$: Weight for cosine similarity support in Policy B (Default `1.0`).
- $\beta$: Weight for measured runtime outcome support in Policy C (Default `1.0`).
- $\lambda_{\text{reg}}$: Asymmetric regression penalty multiplier in Policy C (Default `1.5`, range `1.0` to `3.0`).

### Strict Boundary Rules:
1. **Complete TEST Blindness:** Hyperparameters $\alpha, \beta, \lambda_{\text{reg}}$ must **NEVER** observe or optimize on the held-out TEST partition (`T7`, `T8`).
2. **Tuning on DEV:** Candidate parameter configurations are compared on DEV (`T3`, `T5`) using retrieval memory strictly populated by TRAIN (`T1`, `T2`).
3. **Small-Sample Boundary Acknowledgment:** With 3 DEV cases and 6 TRAIN cases, hyperparameter search is intended to verify algorithmic stability and prevent degenerate weighting, not to claim asymptotic statistical convergence.

---

## 7. Candidate-Key Support Matrix for Held-Out TEST Cases

$$\text{Candidate Key} = (\text{table.lower()}, \text{index\_method.lower()}, \text{tuple(ordered\_columns.lower())})$$

### Test Case Support Against Frozen TRAIN Retrieval Memory (`T1`, `T2`)

| Test Case | Candidate ID | Candidate Index Key | HypoPG Cost Delta | Safety Status | Matching TRAIN Cases (`T1`, `T2`) | Policy Decision Dynamics |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **`CASE-T7-01`**<br>`CASE-T7-02`<br>`CASE-T7-03`<br>(`order_items` compound) | `cand_order_items_quantity_unit_price`<br>`['quantity', 'unit_price']` | `order_items:btree:(quantity, unit_price)` | +97.72% | **Safe** (Baseline) | **0 matches in TRAIN** | **Policy A Default Candidate** (Planner-only choice). |
| | `cand_order_items_quantity`<br>`['quantity']` | +97.74% | **Safe** | **0 matches in TRAIN** (Present in DEV IDs 8, 9) | Fallback to HypoPG cost score (ties with baseline). |
| | `cand_order_items_unit_price`<br>`['unit_price']` | 0.0% | **Ineligible** | **0 matches in TRAIN** | Blocked fail-closed by HypoPG and SafetyAssessor. |
| **`CASE-T8-01`**<br>`CASE-T8-02`<br>(`orders` compound) | `cand_orders_customer_id`<br>`['customer_id']` | `orders:btree:(customer_id,)` | +76.52% | **Safe** (Baseline) | **3 matches in TRAIN** (Memory IDs 1, 2, 3: $\Delta T \approx +83\%$) | **Strong Historical Support** across Policy A, B, and C. |

---

## 8. Partition Lock & Cryptographic Audit Hash

To guarantee that the experimental boundary remains immutable and tamper-evident, the complete machine-readable partition manifest has been serialized and cryptographically hashed:

- **Manifest Path:** [`research/phase6c_partition_manifest.json`](file:///c:/Users/swarsh/Desktop/autodba-research/research/phase6c_partition_manifest.json)
- **Cryptographic Hash Algorithm:** SHA-256
- **Authoritative Hash:** `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`

Any modification to case IDs, template assignments, query texts, or partition boundaries will alter this checksum and invalidate the experiment.

---

## 9. Final Readiness Verdict

# **A. PARTITION LOCKED — READY FOR PHASE 6D**

The evaluation partition is cryptographically locked, 100% compliant with all leakage and retrieval invariants, and fully prepared for **Phase 6D: Comparative A/B/C Execution & Oracle Evaluation**.
