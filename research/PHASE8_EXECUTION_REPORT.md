# Phase 8 Execution Report — Multi-Candidate Unseen-Template Experiment

**Date:** 2026-10-03  
**Run ID:** `20261003T071046Z`  
**Status:** COMPLETED  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Phase 6C Partition SHA-256 (verified):** `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`

---

## 1. Executive Summary

Phase 8 executed one controlled multi-candidate unseen-template experiment for the T9 query:

```sql
SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00
```

Phase 1 produced **3 eligible candidates** (the target pool size for this experiment). All three
were independently HypoPG-validated and safety-eligible. Policy A/B/C selections were frozen in
`phase8_selection_results.json` before any physical index was created. All three candidates were
then benchmarked independently. The oracle was determined post-hoc.

**Result: All three policies agreed. All three selected the composite index
`orders(total_amount, customer_id)`, which was also the oracle.**

---

## 2. Query and Template

| Field | Value |
|:---|:---|
| Raw SQL | `SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00` |
| Canonical template | `select * from orders where customer_id = ? and total_amount >= ?` |
| Template hash (T9) | `8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343` |
| Template ID | T9 (Phase 8 Extension) |
| Target table | `orders` |
| Operator | `>=` (distinct from T3 DEV which uses `>`) |
| Partition role | TEST (Phase 8 Extension — separate from Phase 6D TEST) |

---

## 3. Candidate Generation (Phase 1 Authoritative Diagnosis)

Phase 1 `IntelligenceService.diagnose()` was called directly with `include_rag=False`.

| # | Candidate ID | Canonical Key | is_baseline | HypoPG Cost % | Safety | Eligible |
|:---:|:---|:---|:---:|:---:|:---:|:---:|
| 1 | `cand_orders_total_amount_customer_id` | `orders:btree:total_amount,customer_id` | **True** | **87.55%** | True | **YES** |
| 2 | `cand_orders_total_amount` | `orders:btree:total_amount` | False | 53.70% | True | **YES** |
| 3 | `cand_orders_customer_id` | `orders:btree:customer_id` | False | 76.52% | True | **YES** |

**Total Phase 1 candidates: 3 | Eligible: 3 | Multi-candidate: True | Has baseline: True**

No candidates were added, removed, or modified by this experiment. The pool is the exact
authoritative output of the production pipeline.

---

## 4. Candidate Eligibility

All three candidates passed both eligibility gates:

1. **HypoPG validation**: All three returned `verdict = "validated"` with positive cost improvement.
2. **Safety assessment**: All three returned `eligible_for_approval = True` with no blocking reasons.

---

## 5. Policy A/B/C Selection (Frozen Before Physical Measurement)

**Selection timestamp:** `2026-10-03T07:10:46.853426+00:00`  
**Physical measurement began:** after selection file written.

### Policy A — Planner-Only

| Candidate | composite_score | is_baseline |
|:---|:---:|:---:|
| `(total_amount, customer_id)` | 1.0 (sentinel) | **True** |
| `(total_amount)` | 0.0 | False |
| `(customer_id)` | 0.0 | False |

**Policy A selection: `cand_orders_total_amount_customer_id`**  
Fallback used: No

### Policy B — Similarity-Based (alpha = 1.0)

Policy B accessed TRAIN cases IDs 1–6. `compute_token_hash_similarity()` was applied to match
candidate keys against T1 (customer_id, IDs 1–3) and T2 (total_amount, IDs 4–6).

| Candidate | HypoPG% | sim_support | composite_score | TRAIN matches |
|:---|:---:|:---:|:---:|:---:|
| `(total_amount, customer_id)` | 87.55 | **0.0** | **87.55** | 0 |
| `(customer_id)` | 76.52 | 2.0909 | 78.6109 | 3 (T1) |
| `(total_amount)` | 53.70 | 2.2709 | 55.9709 | 3 (T2) |

**Policy B selection: `cand_orders_total_amount_customer_id`** (score 87.55)  
Fallback used: No (6 matching TRAIN cases total)

> **Key finding:** The composite's HypoPG advantage (+87.55) exceeds the similarity-boosted
> score of `(customer_id)` (76.52 + 2.09 = 78.61) by **~9 points**. The similarity boost for
> single-column candidates was insufficient to overtake the composite's baseline HypoPG lead.

### Policy C — Outcome-Aware (beta = 1.0, lambda_reg = 1.5)

Policy C accessed all 6 TRAIN verified-measured cases. `outcome_support = sum(sim * delta)`
across matching cases.

| Candidate | HypoPG% | outcome_support | composite_score | Measured matches |
|:---|:---:|:---:|:---:|:---:|
| `(total_amount, customer_id)` | 87.55 | **0.0** | **87.55** | 0 |
| `(customer_id)` | 76.52 | 1.7517 | 78.2717 | 3 (T1, verified) |
| `(total_amount)` | 53.70 | 1.7644 | 55.4644 | 3 (T2, verified) |

**Policy C selection: `cand_orders_total_amount_customer_id`** (score 87.55)  
Fallback used: No (6 eligible measured cases)

> **Key finding:** Policy C's outcome_support for `(customer_id)` (+1.7517) raised its score to
> 78.27, still ~9 points short of the composite's 87.55. The empirical outcome signal from TRAIN
> was not strong enough to overtake the composite's HypoPG dominance.

### Selection Agreement Summary

| | Policy A | Policy B | Policy C |
|:---|:---:|:---:|:---:|
| Selected | Composite | Composite | Composite |
| A==B | ✅ | — | — |
| A==C | ✅ | — | — |
| B==C | — | ✅ | — |
| Fallback used | No | No | No |

**All three policies agreed unanimously on the composite index.**

---

## 6. Physical Measurements (W=2, N=10)

Each candidate was benchmarked independently. Index prefix: `idx_autodba_p8_`. All indexes were
dropped and `DISCARD ALL` issued after each measurement.

### Candidate 1: `orders(total_amount, customer_id)` — Composite

| Metric | Value |
|:---|:---:|
| Index name | `idx_autodba_p8_orders_total_amount_customer_id` |
| T_before (mean, N=10) | **3.0016 ms** |
| T_after (mean, N=10) | **1.3041 ms** |
| dT% | **+56.55%** |
| Scan type: before | Seq Scan |
| Scan type: after | **Index Scan** |
| Shared blocks before | 45 |
| Shared blocks after | 3 |
| CoV before | 0.1846 |
| CoV after | 0.3442 |
| Cleanup | OK (0 residual indexes) |

### Candidate 2: `orders(total_amount)` — Single-column range

| Metric | Value |
|:---|:---:|
| Index name | `idx_autodba_p8_orders_total_amount` |
| T_before (mean, N=10) | **2.8263 ms** |
| T_after (mean, N=10) | **1.8263 ms** |
| dT% | **+35.38%** |
| Scan type: before | Seq Scan |
| Scan type: after | Bitmap Heap Scan |
| Shared blocks before | 45 |
| Shared blocks after | 48 |
| CoV before | 0.2387 |
| CoV after | 0.1718 |
| Cleanup | OK (0 residual indexes) |

### Candidate 3: `orders(customer_id)` — Single-column equality

| Metric | Value |
|:---|:---:|
| Index name | `idx_autodba_p8_orders_customer_id` |
| T_before (mean, N=10) | **2.5888 ms** |
| T_after (mean, N=10) | **1.4994 ms** |
| dT% | **+42.08%** |
| Scan type: before | Seq Scan |
| Scan type: after | Bitmap Heap Scan |
| Shared blocks before | 45 |
| Shared blocks after | 12 |
| CoV before | 0.2027 |
| CoV after | 0.2236 |
| Cleanup | OK (0 residual indexes) |

### Physical Measurement Rankings

| Rank | Candidate | Measured dT% | Scan Type After | Shared Blocks After |
|:---:|:---|:---:|:---:|:---:|
| 1st | `(total_amount, customer_id)` — composite | **+56.55%** | Index Scan | 3 |
| 2nd | `(customer_id)` | +42.08% | Bitmap Heap Scan | 12 |
| 3rd | `(total_amount)` | +35.38% | Bitmap Heap Scan | 48 |

**The composite achieved the highest realized improvement and triggered a direct Index Scan
(vs. Bitmap Heap Scan for both single-column candidates).** This confirms the composite covers
both predicates efficiently, allowing the planner to use a pure index scan with dramatically
reduced block I/O (3 vs. 45–48 shared blocks).

---

## 7. Oracle Determination

The oracle is the candidate with the maximum realized `runtime_improvement_percent`:

**Oracle: `cand_orders_total_amount_customer_id` — `+56.55%`**  
No tie detected.

Oracle timestamp: determined after all 3 independent measurements were complete.  
Oracle was determined post-hoc and had **zero influence** on the frozen policy selections.

---

## 8. Policy vs Oracle Comparison

| Policy | Selected | dT% Achieved | Oracle dT% | Regret | Oracle Agreement |
|:---:|:---|:---:|:---:|:---:|:---:|
| **A** | `(total_amount, customer_id)` | **+56.55%** | +56.55% | **0.00%** | ✅ |
| **B** | `(total_amount, customer_id)` | **+56.55%** | +56.55% | **0.00%** | ✅ |
| **C** | `(total_amount, customer_id)` | **+56.55%** | +56.55% | **0.00%** | ✅ |

**All three policies achieved zero regret and unanimous oracle agreement.**

---

## 9. HypoPG vs Physical Outcome Analysis

| Candidate | HypoPG Cost % | Physical dT% | HypoPG Overestimates By |
|:---|:---:|:---:|:---:|
| `(total_amount, customer_id)` | 87.55% | 56.55% | +31.0 pp |
| `(customer_id)` | 76.52% | 42.08% | +34.4 pp |
| `(total_amount)` | 53.70% | 35.38% | +18.3 pp |

All HypoPG estimates overestimated realized improvement. The **ordinal ranking is preserved**
(composite > customer_id > total_amount) — a consistent finding with prior phases.

---

## 10. Policy Behaviour Analysis

### Why Policies B and C Did Not Diverge

Policy B and C each had TRAIN evidence for `(customer_id)` and `(total_amount)` but **zero
TRAIN evidence for the composite** (the DEV-only composite case, ID 7, was correctly excluded).
Despite this structural asymmetry:

- **Policy B**: Similarity boost for `(customer_id)` was +2.09 → composite score 78.61.
  Composite had score 87.55. Gap of **~9 points** — too large for similarity alone to bridge.
- **Policy C**: Outcome support for `(customer_id)` was +1.75 → composite score 78.27.
  Composite had score 87.55. Gap of **~9 points** — too large for outcome evidence to bridge.

The composite's HypoPG dominance (87.55 vs. 76.52 for the next best) was **~11 percentage
points larger than the single-column candidates' starting base**, and the TRAIN evidence
contributed only ~2 points per candidate. HypoPG signal dominated at alpha=beta=1.0.

### Implications for Policy Design

This case demonstrates that **a large HypoPG advantage on the composite acts as a natural
barrier** against single-column candidate promotion — even when those candidates have 3 verified
TRAIN matches. Policies B and C would need alpha/beta significantly larger (or the composite's
HypoPG advantage to be smaller, e.g. <10pp) to produce divergence in this scenario.

---

## 11. Database State Verification

| Check | Expected | Actual | OK? |
|:---|:---:|:---:|:---:|
| `optimization_memories` count | 14 | 14 | ✅ |
| Memory IDs 1–14 intact | Yes | Yes | ✅ |
| Residual `idx_autodba_p8_*` indexes | 0 | 0 | ✅ |
| T9 outcomes written to memories | No | No | ✅ |

---

## 12. Methodological Limitation

> **This is ONE informative multi-candidate unseen-template case (N=1).** The experiment confirms
> that:
> 1. The pipeline can produce multiple eligible candidates for a two-predicate integer+float query.
> 2. All three policies agree when the composite's HypoPG advantage exceeds the TRAIN similarity
>    and outcome boosts by a large margin.
> 3. Policy B and C accessed TRAIN evidence correctly (no fallback, correct exclusion of DEV).
>
> **What cannot be concluded:** Whether Policies B or C are better than A in general.
> A single case of unanimous agreement provides no discriminative evidence.
> To observe divergence, future cases should be designed where the HypoPG gap between
> baseline and alternatives is smaller (e.g., <10 percentage points).

---

## 13. Artifacts Created by This Execution

| Artifact | Path | Status |
|:---|:---|:---:|
| Selection results (pre-measurement) | `research/phase8_selection_results.json` | Written |
| Physical measurements | `research/phase8_measurements.json` | Written |
| Execution report | `research/PHASE8_EXECUTION_REPORT.md` | This file |
| Final audit | `research/PHASE8_FINAL_AUDIT.md` | Written |
| Execution script | `research/execute_phase8.py` | Written |

---

## 14. Sequencing Verification

| Step | Timestamp |
|:---|:---|
| Policy selections frozen (written to JSON) | `2026-10-03T07:10:46.853426+00:00` |
| Composite index benchmarked | After above timestamp |
| total_amount index benchmarked | After above timestamp |
| customer_id index benchmarked | After above timestamp |
| Oracle determined | After all 3 benchmarks |

The selection timestamp in `phase8_selection_results.json` predates all physical measurements.
The oracle was determined after all measurements completed.
