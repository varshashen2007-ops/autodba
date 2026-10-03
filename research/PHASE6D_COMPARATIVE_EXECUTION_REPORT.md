# Phase 6D: Comparative A/B/C Execution & Oracle Evaluation Report

**Date:** 2026-10-01  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Database Host:** `localhost:5432` (`autodba-main-postgres-1` / PostgreSQL 17.11)  
**Partition Manifest SHA-256:** `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`  
**Status:** COMPLETED — READY FOR EMPIRICAL SYNTHESIS (Zero database mutations, zero commits)

---

## 1. Executive Summary & Experimental Overview

Phase 6D executed the comparative evaluation across three distinct candidate selection policies on the held-out **TEST partition** (`T7`, `T8` — 5 cases):
1. **Policy A (Planner-Only Baseline):** Selects the Phase 1 default candidate based strictly on heuristic plan node properties and HypoPG simulated cost reduction.
2. **Policy B (Similarity-Based Retrieval):** Evaluates token-hash cosine similarity support from historical cases in the frozen **TRAIN** partition.
3. **Policy C (Outcome-Aware Retrieval):** Ranks candidates by combining HypoPG simulated cost reduction with empirical runtime outcome support from verified measured **TRAIN** cases.
4. **Empirical Oracle ($c^*$):** Determined independently by physically creating and benchmarking **every eligible candidate** on the live PostgreSQL engine:
   $$c^*(q) = \arg\max_{c \in C_{\text{eligible}}(q)} \Delta T_{\text{meas}}(c, q)$$

### Critical Invariant Confirmations:
- **Offline Selection Order:** Policy decisions $c_A, c_B, c_C$ were computed offline and locked in `research/phase6d_selection_results.json` **before** any physical test measurements were conducted.
- **Retrieval Boundary:** Historical retrieval for Policies B and C was strictly restricted to **TRAIN** cases (Memory IDs 1–6). DEV and TEST cases were never exposed to the retriever.
- **Zero Database Memory Contamination:** TEST measurements were recorded solely in research artifacts (`research/phase6d_measurements.json`) and **never persisted** to the live `optimization_memories` table (which retains exactly 14 records).
- **Physical Cleanup:** All transient indexes were torn down immediately after benchmarking. Verified 0 residual `idx_autodba_*` indexes.

---

## 2. Experimental Manifest & Locked Hyperparameters

- **Experiment Manifest:** [`research/phase6d_experiment_manifest.json`](file:///c:/Users/swarsh/Desktop/autodba-research/research/phase6d_experiment_manifest.json)
- **Selection Manifest:** [`research/phase6d_selection_results.json`](file:///c:/Users/swarsh/Desktop/autodba-research/research/phase6d_selection_results.json)
- **Measurements Artifact:** [`research/phase6d_measurements.json`](file:///c:/Users/swarsh/Desktop/autodba-research/research/phase6d_measurements.json)
- **Locked Hyperparameters:**
  - $\alpha$ (similarity weight): `1.0`
  - $\beta$ (outcome weight): `1.0`
  - $\lambda_{\text{reg}}$ (asymmetric regression penalty): `1.5`

---

## 3. Comprehensive Per-Case Comparative Results

```
LEGEND:
- Delta T%: Empirical runtime improvement percentage (((T_before - T_after) / T_before) * 100)
- Regret%: Selection regret relative to Oracle (Oracle Delta - Policy Delta)
- OA: Oracle Agreement (True/False)
```

| Test Case ID | Template | Query SQL | Eligible Candidates Evaluated | Selected Policy A | Selected Policy B | Selected Policy C | Empirical Oracle ($c^*$) | Policy A $\Delta T\%$ (Regret) | Policy B $\Delta T\%$ (Regret) | Policy C $\Delta T\%$ (Regret) | Oracle $\Delta T\%$ |
| :--- | :---: | :--- | :---: | :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| **`CASE-T7-01`** | `T7` | `order_items WHERE qty>7 AND price>80` | 2 | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity, unit_price)` | **+63.49%** (0.00%) [OA=✅] | **+63.49%** (0.00%) [OA=✅] | **+63.49%** (0.00%) [OA=✅] | **+63.49%** |
| **`CASE-T7-02`** | `T7` | `order_items WHERE qty>8 AND price>85` | 2 | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity)` | **+47.01%** (3.88%) [OA=❌] | **+47.01%** (3.88%) [OA=❌] | **+47.01%** (3.88%) [OA=❌] | **+50.89%** |
| **`CASE-T7-03`** | `T7` | `order_items WHERE qty>6 AND price>90` | 2 | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity, unit_price)` | `(quantity)` | **+56.23%** (2.43%) [OA=❌] | **+56.23%** (2.43%) [OA=❌] | **+56.23%** (2.43%) [OA=❌] | **+58.66%** |
| **`CASE-T8-01`** | `T8` | `orders WHERE cust_id=42 AND status=COMP` | 1 | `(customer_id)` | `(customer_id)` | `(customer_id)` | `(customer_id)` | **+43.49%** (0.00%) [OA=✅] | **+43.49%** (0.00%) [OA=✅] | **+43.49%** (0.00%) [OA=✅] | **+43.49%** |
| **`CASE-T8-02`** | `T8` | `orders WHERE cust_id=105 AND status=SHIP` | 1 | `(customer_id)` | `(customer_id)` | `(customer_id)` | `(customer_id)` | **+1.35%** (0.00%) [OA=✅] | **+1.35%** (0.00%) [OA=✅] | **+1.35%** (0.00%) [OA=✅] | **+1.35%** |

---

## 4. Candidate-Level Physical Benchmark Telemetry

All benchmarks executed with $W=2$ warmup runs and $N=10$ measured runs on PostgreSQL 17.11:

### Template T7 (`order_items` compound queries):
1. **`CASE-T7-01`:**
   - Candidate `order_items(quantity, unit_price)` (composite baseline): $T_{\text{before}} = 1.7686\text{ ms}$, $T_{\text{after}} = 0.6457\text{ ms} \rightarrow \mathbf{\Delta T = +63.49\%}$ [⭐ **Oracle**]
   - Candidate `order_items(quantity)` (single-column): $T_{\text{before}} = 1.0988\text{ ms}$, $T_{\text{after}} = 0.6031\text{ ms} \rightarrow \mathbf{\Delta T = +45.12\%}$
2. **`CASE-T7-02`:**
   - Candidate `order_items(quantity, unit_price)` (composite baseline): $T_{\text{before}} = 1.1589\text{ ms}$, $T_{\text{after}} = 0.6141\text{ ms} \rightarrow \mathbf{\Delta T = +47.01\%}$
   - Candidate `order_items(quantity)` (single-column): $T_{\text{before}} = 1.0827\text{ ms}$, $T_{\text{after}} = 0.5317\text{ ms} \rightarrow \mathbf{\Delta T = +50.89\%}$ [⭐ **Oracle**]
3. **`CASE-T7-03`:**
   - Candidate `order_items(quantity, unit_price)` (composite baseline): $T_{\text{before}} = 1.1058\text{ ms}$, $T_{\text{after}} = 0.4840\text{ ms} \rightarrow \mathbf{\Delta T = +56.23\%}$
   - Candidate `order_items(quantity)` (single-column): $T_{\text{before}} = 1.0997\text{ ms}$, $T_{\text{after}} = 0.4546\text{ ms} \rightarrow \mathbf{\Delta T = +58.66\%}$ [⭐ **Oracle**]

### Template T8 (`orders` compound queries):
4. **`CASE-T8-01`:**
   - Candidate `orders(customer_id)` (baseline): $T_{\text{before}} = 0.8541\text{ ms}$, $T_{\text{after}} = 0.4826\text{ ms} \rightarrow \mathbf{\Delta T = +43.49\%}$ [⭐ **Oracle**]
5. **`CASE-T8-02`:**
   - Candidate `orders(customer_id)` (baseline): $T_{\text{before}} = 0.6988\text{ ms}$, $T_{\text{after}} = 0.6894\text{ ms} \rightarrow \mathbf{\Delta T = +1.35\%}$ [⭐ **Oracle**]

---

## 5. Summary Evaluation Metrics

| Metric | Policy A (Planner-Only) | Policy B (Similarity) | Policy C (Outcome-Aware) | Empirical Oracle |
| :--- | :---: | :---: | :---: | :---: |
| **Mean Measured Runtime Improvement ($\bar{\Delta T}\%$)** | **42.31%** | **42.31%** | **42.31%** | **43.58%** |
| **Mean Selection Regret** | **1.26%** | **1.26%** | **1.26%** | **0.00%** |
| **Oracle Top-1 Agreement Rate** | **3 / 5 (60.0%)** | **3 / 5 (60.0%)** | **3 / 5 (60.0%)** | **5 / 5 (100%)** |
| **Regression Rate ($R_{\text{reg}}\%$)** | **0.0%** (0 / 5) | **0.0%** (0 / 5) | **0.0%** (0 / 5) | **0.0%** |
| **Fallback Frequency** | **0.0%** (0 / 5) | **100.0%** (5 / 5) | **100.0%** (5 / 5) | N/A |
| **Safety Violation Rate** | **0.0%** (0 / 5) | **0.0%** (0 / 5) | **0.0%** (0 / 5) | **0.0%** |
| **Clean Physical Index Teardown Rate** | **100.0%** | **100.0%** | **100.0%** | **100.0%** |

---

## 6. Algorithmic Dynamics & Retrieval Fallback Analysis

### Why Policies A, B, and C Selected the Same Candidates:
1. **Strict Exact Key Matching Rule:**
   $$\text{Candidate Key} = (\text{table.lower()}, \text{index\_method.lower()}, \text{tuple(ordered\_columns.lower())})$$
2. **TRAIN vs TEST Relation Disparity:**
   - The frozen **TRAIN** partition contains historical cases strictly on `orders` (Memory IDs 1–3 on `orders(customer_id)`, IDs 4–6 on `orders(total_amount)`).
   - Test Template `T7` queries filter on table `order_items` (`quantity, unit_price`).
   - Because zero historical cases in TRAIN match relation `order_items`, `CandidateSelector` detected zero matching candidate keys in TRAIN.
3. **Fail-Safe Deterministic Fallback Activation:**
   - In accordance with the system design, when no historical evidence exists to differentiate candidates, **Policy B and Policy C deterministically fall back to Policy A** (the default baseline candidate).
   - This prevented arbitrary or hallucinated ranking adjustments in the absence of valid training evidence.
4. **Template T8 Dynamics:**
   - On `T8` (`orders WHERE customer_id = ? AND status = ?`), only a single candidate (`orders(customer_id)`) was eligible.
   - All three policies deterministically agreed on `orders(customer_id)`.

---

## 7. Limitations & Scientific Caveats

1. **No Claims of Superiority:** Outcome-aware ranking did not outperform the planner baseline on this test set because the cross-table test queries (`order_items`) had no exact candidate key matches in the `orders`-only TRAIN partition, activating the fail-safe fallback.
2. **No Claims of Statistical Significance:** With 5 test cases, metrics demonstrate algorithmic verification and fail-safe safety behavior rather than asymptotic power.
3. **Oracle Dynamics:** The empirical oracle demonstrated that for 2 of 3 multi-candidate queries (`CASE-T7-02`, `CASE-T7-03`), single-column indexing on `quantity` achieved slightly higher empirical speedup ($+50.89\%$ and $+58.66\%$) than composite indexing ($+47.01\%$ and $+56.23\%$), incurring a modest selection regret of $1.26\%$.
4. **Buffer Cache Persistence:** Shared buffers retain cached pages across benchmarks; while $W=2$ warmups and `DISCARD ALL` mitigate session plan bleed, memory locality remains present.

---

## 8. Final Verdict

# **A. PHASE 6D EXECUTED — READY FOR RESULTS ANALYSIS**
