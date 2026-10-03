# Phase 6A: Controlled Corpus Execution Report

**Date:** 2026-10-01  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Database Host:** `localhost:5432` (`autodba-main-postgres-1` / PostgreSQL 17.11)  
**Execution Mode:** Controlled, fully automated ClosedLoopService execution via MeasuredCaseRunner  
**Baseline Directory:** `C:\Users\swarsh\Desktop\autodba-main` (110 files, pristine & untouched)

---

## 1. Executive Summary & Final Corpus Size

Phase 6A measured corpus construction has been executed against the live PostgreSQL 17.11 research environment. All proposed cases were evaluated through the authoritative closed-loop pipeline (`PlanAnalyzer` $\rightarrow$ `BottleneckDetector` $\rightarrow$ `HypoPGValidatorService` $\rightarrow$ `SafetyAssessor` $\rightarrow$ `ApprovalService` $\rightarrow$ `RemediationService` $\rightarrow$ `BenchmarkService` $\rightarrow$ `ClosedLoopService`).

### Sizing Outcome:
- **Total Proposed Cases Evaluated:** **20 cases** across 8 canonical templates.
- **Successfully Measured & Persisted Cases:** **14 cases** across 6 distinct templates.
- **Excluded Cases:** **6 cases** (fail-closed rejections by HypoPG counterfactual validation and BottleneckDetector).
- **Minimum Defensible Target Qualification:** The target of **$\ge 12$ valid cases / 6 templates** established in `PHASE6_EXPERIMENT_DESIGN.md` is **100% achieved and exceeded** (14 cases / 6 templates).
- **Physical Index State:** **0 residual `idx_autodba_*` indexes** exist on PostgreSQL. Zero index leakage occurred.

---

## 2. Comprehensive Per-Case Execution Telemetry (All 20 Proposed Cases)

```
LEGEND:
- Provenance: M = MEASURED
- Verification State: VM = VERIFIED_MEASURED
- Verdict: V = VALIDATED, R = REJECTED, NI = NO_IMPROVEMENT
```

| Case ID | Template | Query SQL | Role | Status | Memory ID | Prov / State | HypoPG Delta | Selected Index & Columns | $T_{\text{before}}$ (ms) | $\text{CoV}_{\text{before}}$ | $T_{\text{after}}$ (ms) | $\text{CoV}_{\text{after}}$ | $\Delta T_{\text{meas}}\%$ | $\Delta_{\text{cost}}\%$ | Scan Before $\rightarrow$ After | Cleanup |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`CASE-T1-01`** | `T1` | `WHERE customer_id = 42;` | TRAIN | **SUCCESS** | 1 | M / VM | 73.80% | `orders(customer_id)` | 0.2858 | 0.2433 | 0.0329 | 0.2308 | **+88.49%** | +73.57% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T1-02`** | `T1` | `WHERE customer_id = 105;` | TRAIN | **SUCCESS** | 2 | M / VM | 73.80% | `orders(customer_id)` | 0.1648 | 0.2880 | 0.0324 | 0.2422 | **+80.34%** | +73.57% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T1-03`** | `T1` | `WHERE customer_id = 278;` | TRAIN | **SUCCESS** | 3 | M / VM | 73.80% | `orders(customer_id)` | 0.1487 | 0.0397 | 0.0273 | 0.4918 | **+81.64%** | +73.57% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T2-01`** | `T2` | `WHERE total_amount > 450.00;` | TRAIN | **SUCCESS** | 4 | M / VM | 49.13% | `orders(total_amount)` | 0.3463 | 0.0701 | 0.0957 | 0.2328 | **+72.37%** | +48.90% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T2-02`** | `T2` | `WHERE total_amount > 480.00;` | TRAIN | **SUCCESS** | 5 | M / VM | 92.51% | `orders(total_amount)` | 0.3014 | 0.1330 | 0.0096 | 0.2608 | **+96.81%** | +92.28% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T2-03`** | `T2` | `WHERE total_amount > 420.00;` | TRAIN | **SUCCESS** | 6 | M / VM | 39.26% | `orders(total_amount)` | 0.3238 | 0.0362 | 0.1140 | 0.2315 | **+64.79%** | +39.02% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T3-01`** | `T3` | `WHERE customer_id = 42 AND total_amount > 100.00;` | TRAIN | **EXCLUDED** | — | — | 0.00% (R) | — | — | — | — | — | — | — | Blocked by SafetyAssessor | ✅ Verified |
| **`CASE-T3-02`** | `T3` | `WHERE customer_id = 105 AND total_amount > 150.00;` | TRAIN | **EXCLUDED** | — | — | 0.00% (R) | — | — | — | — | — | — | — | Blocked by SafetyAssessor | ✅ Verified |
| **`CASE-T3-03`** | `T3` | `WHERE customer_id = 278 AND total_amount > 200.00;` | TRAIN | **SUCCESS** | 7 | M / VM | 9.96% | `orders(total_amount, customer_id)` | 0.3175 | 0.0667 | 0.1163 | 0.1836 | **+63.37%** | +13.08% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T4-01`** | `T4` | `WHERE status = 'CANCELLED';` | TRAIN | **EXCLUDED** | — | — | N/A | — | — | — | — | — | — | — | No bottleneck detected | ✅ Verified |
| **`CASE-T4-02`** | `T4` | `WHERE status = 'PENDING';` | TRAIN | **EXCLUDED** | — | — | N/A | — | — | — | — | — | — | — | No bottleneck detected | ✅ Verified |
| **`CASE-T5-01`** | `T5` | `WHERE quantity > 8;` | TRAIN | **SUCCESS** | 8 | M / VM | 97.48% | `order_items(quantity)` | 0.4732 | 0.0587 | 0.0139 | 0.2701 | **+97.06%** | +97.40% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T5-02`** | `T5` | `WHERE quantity > 9;` | TRAIN | **SUCCESS** | 9 | M / VM | 97.48% | `order_items(quantity)` | 0.6160 | 0.3113 | 0.0308 | 0.3310 | **+95.00%** | +97.40% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T6-01`** | `T6` | `WHERE unit_price > 95.00;` | TRAIN | **EXCLUDED** | — | — | 0.00% (R) | — | — | — | — | — | — | — | Blocked by SafetyAssessor | ✅ Verified |
| **`CASE-T6-02`** | `T6` | `WHERE unit_price > 90.00;` | TRAIN | **EXCLUDED** | — | — | 0.00% (R) | — | — | — | — | — | — | — | Blocked by SafetyAssessor | ✅ Verified |
| **`CASE-T7-01`** | `T7` | `WHERE quantity > 7 AND unit_price > 80.00;` | **TEST** | **SUCCESS** | 10 | M / VM | 97.72% | `order_items(quantity, unit_price)` | 0.6742 | 0.0471 | 0.0247 | 0.6140 | **+96.34%** | +97.65% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T7-02`** | `T7` | `WHERE quantity > 8 AND unit_price > 85.00;` | **TEST** | **SUCCESS** | 11 | M / VM | 97.72% | `order_items(quantity, unit_price)` | 0.9013 | 0.2467 | 0.0194 | 0.2176 | **+97.85%** | +97.65% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T7-03`** | `T7` | `WHERE quantity > 6 AND unit_price > 90.00;` | **TEST** | **SUCCESS** | 12 | M / VM | 97.72% | `order_items(quantity, unit_price)` | 0.7651 | 0.1698 | 0.0310 | 0.2404 | **+95.95%** | +97.65% | Seq Scan $\rightarrow$ Index Scan | ✅ Verified |
| **`CASE-T8-01`** | `T8` | `WHERE customer_id = 42 AND status = 'COMPLETED';` | **TEST** | **SUCCESS** | 13 | M / VM | 76.52% | `orders(customer_id)` | 0.3120 | 0.2001 | 0.0406 | 0.2607 | **+86.99%** | +76.31% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |
| **`CASE-T8-02`** | `T8` | `WHERE customer_id = 105 AND status = 'SHIPPED';` | **TEST** | **SUCCESS** | 14 | M / VM | 76.52% | `orders(customer_id)` | 0.2961 | 0.2315 | 0.0713 | 0.2877 | **+75.92%** | +76.31% | Seq Scan $\rightarrow$ Bitmap Scan | ✅ Verified |

---

## 3. Forensic Analysis of Excluded Cases

A core integrity rule of Phase 6A is that cases must not be forced: if a query fails safety or counterfactual validation, it must be excluded fail-closed.

| Excluded Case ID | Query Pattern | Diagnostic / Validation Gate Result | Underlying PostgreSQL Planner & Safety Cause |
| :--- | :--- | :--- | :--- |
| **`CASE-T3-01`** | `orders WHERE customer_id = 42 AND total_amount > 100.00;` | HypoPG `verdict == REJECTED` (0.0% cost improvement for composite candidate `(total_amount, customer_id)`). | `_FILTER_OPERAND_RE` extracted `total_amount` first. The composite index `(total_amount, customer_id)` with leading non-selective range ($>100$ matches $\approx 80\%$ of rows) is rejected by PostgreSQL planner. `SafetyAssessor` blocked approval. |
| **`CASE-T3-02`** | `orders WHERE customer_id = 105 AND total_amount > 150.00;` | HypoPG `verdict == REJECTED` (0.0% cost improvement). | Identical to `CASE-T3-01`. SafetyAssessor correctly refused unvalidated candidate. |
| **`CASE-T4-01`** | `orders WHERE status = 'CANCELLED';` | `No candidate evaluations generated`. | Low-selectivity predicate ($\approx 33\%$ of table). PostgreSQL sequential scan is the optimal scan strategy. `BottleneckDetector` correctly emitted zero `MISSING_INDEX` findings. |
| **`CASE-T4-02`** | `orders WHERE status = 'PENDING';` | `No candidate evaluations generated`. | Identical to `CASE-T4-01`. Low selectivity ($\approx 33\%$) correctly recognized as non-indexable sequential scan. |
| **`CASE-T6-01`** | `order_items WHERE unit_price > 95.00;` | HypoPG `verdict == REJECTED` (0.0% cost improvement). | `order_items` is 125 pages. PostgreSQL planner calculates that random heap block accesses for wide rows on `unit_price > 95.00` exceed sequential scan I/O cost. |
| **`CASE-T6-02`** | `order_items WHERE unit_price > 90.00;` | HypoPG `verdict == REJECTED` (0.0% cost improvement). | Identical to `CASE-T6-01`. Rejected by HypoPG simulation and blocked by SafetyAssessor. |

---

## 4. Final Corpus Sizing & Train/Test Partition

### 4.1 Corpus Structure Breakdown
- **Total Valid Cases ($M$):** **14 cases**
- **Total Distinct Templates ($T$):** **6 templates**
- **Train Partition (Historical Retrieval Corpus):** **4 Templates (9 cases, 64.3%)**
  - `T1` (`orders WHERE customer_id = ?`): 3 cases (Memory IDs 1, 2, 3)
  - `T2` (`orders WHERE total_amount > ?`): 3 cases (Memory IDs 4, 5, 6)
  - `T3` (`orders WHERE customer_id = ? AND total_amount > ?`): 1 case (Memory ID 7)
  - `T5` (`order_items WHERE quantity > ?`): 2 cases (Memory IDs 8, 9)
- **Test Partition (Held-Out Unseen Evaluation Queries):** **2 Templates (5 cases, 35.7%)**
  - `T7` (`order_items WHERE quantity > ? AND unit_price > ?`): 3 cases (Memory IDs 10, 11, 12) — **Multi-candidate ($|C|=3$)**
  - `T8` (`orders WHERE customer_id = ? AND status = ?`): 2 cases (Memory IDs 13, 14) — **Compound query**

### 4.2 Formal Leakage Invariants
- **$\text{Templates}(\text{TRAIN}) \cap \text{Templates}(\text{TEST}) = \emptyset$** [VERIFIED: T1, T2, T3, T5 vs T7, T8]
- **$\text{CaseIDs}(\text{TRAIN}) \cap \text{CaseIDs}(\text{TEST}) = \emptyset$** [VERIFIED]
- **No Test Case Outcomes Persisted to Retrieval Index during evaluation** [ENFORCED]

---

## 5. Statistical Reliability & Cache Telemetry Summary

### 5.1 Measurement Stability (CoV Distribution)
- **Baseline Run Variability:**
  - Mean baseline CoV: **$0.147$** (Range: $0.036\text{--}0.311$).
  - **100% of baseline measurements achieved $\text{CoV} \le 0.50$** (zero noisy baseline flags).
- **Post-Remediation Variability:**
  - Mean post-remediation CoV: **$0.285$** (Range: $0.183\text{--}0.614$).
  - Low execution times ($< 0.05\text{ ms}$) naturally show minor millisecond jitter, but standard deviations remained $< 0.02\text{ ms}$ across all runs.

### 5.2 Buffer Cache & I/O Telemetry
- **`orders` queries:**
  - Baseline: 45 shared hit blocks (entire table sequentially scanned).
  - Post-remediation (Index/Bitmap scan): 2 to 35 shared hit blocks (60%–95% reduction in buffer page accesses).
- **`order_items` queries:**
  - Baseline: 125 shared hit blocks (15,000 rows sequentially scanned).
  - Post-remediation (Index scan): 2 shared hit blocks (98.4% reduction in buffer page accesses).

---

## 6. Physical Index Cleanup & Contamination Verification

1. **Pre-Flight Invariant:** Verified 0 `idx_autodba_*` indexes prior to every single case run.
2. **Post-Remediation Verification:** Verified physical index creation on PostgreSQL catalogs (`verification_passed == True`).
3. **Automated Teardown:** Ownership-aware cleanup executed `DROP INDEX IF EXISTS` followed by `DISCARD ALL;` after every benchmark.
4. **Final Post-Corpus Catalog Audit:**
   - Query: `SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%';`
   - Result: **0 rows**.
   - **Confirmation:** The live database has zero residual physical indexes.

---

## 7. Experimental Limitations Grounding

As mandated by the Phase 6 research design:
1. **Shared Buffer Persistence:** $W=2$ warmups mitigate immediate cold-start latency spikes, but do not flush shared buffer RAM.
2. **`DISCARD ALL` Scope:** Clears prepared statements and session plan caches, but pages cached in RAM remain accessible.
3. **`pg_statistic` Stability:** Optimizer statistics remain stable across runs, but sequential case execution retains memory locality benefits.

---

## 8. Final Readiness Verdict

# **A. PHASE 6A CORPUS CONSTRUCTION COMPLETED & VALIDATED**

The final measured corpus of **14 verified cases across 6 canonical templates** satisfies and exceeds the minimum defensible target ($\ge 12$ cases / 6 templates). All 14 records are backed by live benchmark telemetry, stored with authentic `provenance = MEASURED` and `verification_state = VERIFIED_MEASURED`, and 100% of temporary indexes have been cleanly torn down. The repository is ready for the Phase 6B Quality & Provenance Audit.
