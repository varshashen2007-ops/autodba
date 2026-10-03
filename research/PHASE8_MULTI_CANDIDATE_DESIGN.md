# Phase 8: Multi-Candidate Selection Experiment Design

**Date:** 2026-10-03  
**Status:** DESIGN — AWAITING PRE-EXECUTION AUDIT SIGN-OFF  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Phase 6C Partition Lock SHA-256:** `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`

> [!IMPORTANT]
> This document is a **research design artifact only**. No physical CREATE INDEX, benchmarking,
> or optimization_memories writes are authorized until this design passes the pre-execution audit
> and all leakage, parameter-lock, and oracle-sequencing controls are verified.

---

## 1. Research Question

**Can historical similarity/outcome evidence change candidate selection for an unseen PostgreSQL
query pattern when multiple candidates are independently HypoPG-validated and safety-eligible?**

More precisely: given a TEST query whose canonical template has never appeared in TRAIN or DEV,
and given three independently validated candidate indexes, does Policy B (similarity-based) or
Policy C (outcome-aware) select a different candidate than Policy A (planner-only), and does
that difference produce better or worse realized runtime improvement?

This is the first Phase 8 case where the candidate pool size |C| = 3, making genuine policy
divergence structurally possible.

### Sub-questions

1. Does Policy B's similarity-weighted HypoPG score change the ranking relative to Policy A's
   planner-cost-only selection?
2. Does Policy C's empirical outcome evidence from TRAIN change the ranking relative to Policy A?
3. If Policy B ≠ Policy A or Policy C ≠ Policy A: does the selected candidate achieve higher
   realized dT% than the policy-A baseline choice?
4. Does the composite index `(total_amount, customer_id)` — which has NO TRAIN support — lose
   ground to the single-column candidates when similarity/outcome signal is incorporated?

---

## 2. Query Under Test

### Raw SQL

```sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND total_amount >= 450.00;
```

### Canonical Template (via `canonicalize_sql()`)

```
select * from orders where customer_id = ? and total_amount >= ?
```

> [!NOTE]
> `canonicalize_sql()` in `research/case_schema.py` lines 90–93 normalizes spacing around
> comparison operators but **preserves the operator itself**. The rule `>= ` is preserved as
> `>=`. Therefore `>= 450.00` canonicalizes to `>= ?`, which is structurally distinct from
> `> ?` (the T3 DEV template).

### Template ID

**T9** (new, Phase 8 extension)

### Canonical Template Hash

SHA-256 of `"select * from orders where customer_id = ? and total_amount >= ?"`:

```
[TO BE COMPUTED AND LOCKED IN MANIFEST — see phase8_experiment_manifest.json]
```

Computation method: `hashlib.sha256(canonicalize_sql(sql).encode("utf-8")).hexdigest()`
using the exact `canonicalize_sql` implementation in `research/case_schema.py`.

### Relation to Existing Templates

| Template | Operator | Canonical Form | Partition | Status |
|:---|:---:|:---|:---:|:---|
| **T1** | `=` | `select * from orders where customer_id = ?` | TRAIN | Existing |
| **T2** | `>` | `select * from orders where total_amount > ?` | TRAIN | Existing |
| **T3** | `>` | `select * from orders where customer_id = ? and total_amount > ?` | DEV | Existing |
| **T9** | `>=` | `select * from orders where customer_id = ? and total_amount >= ?` | TEST (Phase 8) | **NEW** |

**T9 ≠ T3**: The `>=` vs `>` operator difference generates different template hashes under the
project's canonicalization rules. T9 is not present in TRAIN, DEV, or the Phase 6C TEST partition.

---

## 3. Candidate Set

The authoritative runtime diagnostic produced exactly three candidate evaluations:

| # | Candidate ID | Canonical Key | Columns | HypoPG Cost Before | HypoPG Cost After | HypoPG % | Safety | is_baseline |
|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|
| 1 | `cand_orders_total_amount_customer_id` | `orders:btree:(total_amount,customer_id)` | `(total_amount, customer_id)` | 120.0 | 14.94 | **87.55%** | ✅ | **True** |
| 2 | `cand_orders_total_amount` | `orders:btree:(total_amount,)` | `(total_amount)` | 120.0 | 55.56 | **53.70%** | ✅ | False |
| 3 | `cand_orders_customer_id` | `orders:btree:(customer_id,)` | `(customer_id)` | 120.0 | 28.18 | **76.52%** | ✅ | False |

**Pool size |C| = 3.** All three candidates are HypoPG-validated and safety-eligible.

> [!IMPORTANT]
> The composite `(total_amount, customer_id)` is the Phase 1 baseline (`is_baseline=True`).
> This is the candidate that Policy A will select deterministically.

### Candidate Key Canonicalization

Per `canonical_candidate_key()` in `research/candidate_selector.py` (lines 36–51):

```python
(table_name.strip().lower(), index_method.strip().lower(), tuple(col.strip().lower() for col in columns))
```

| Candidate | Canonical Tuple |
|:---|:---|
| `(total_amount, customer_id)` composite | `("orders", "btree", ("total_amount", "customer_id"))` |
| `(total_amount)` single | `("orders", "btree", ("total_amount",))` |
| `(customer_id)` single | `("orders", "btree", ("customer_id",))` |

---

## 4. Partition Role

| Partition | Role in Phase 8 | Templates | Memory IDs |
|:---:|:---|:---|:---|
| **TRAIN** | Historical retrieval corpus (frozen) | T1, T2 | 1, 2, 3, 4, 5, 6 |
| **DEV** | Hyperparameter validation (frozen, Phase 6D) | T3, T5 | 7, 8, 9 |
| **TEST (Phase 8)** | Single unseen evaluation case | **T9** (new) | None (not in memories yet) |

The Phase 8 TEST case is a **new extension partition** separate from the Phase 6D TEST partition
(which contains T7 and T8). The Phase 6D TEST partition is frozen and immutable. Phase 8 creates
a standalone single-case extension.

---

## 5. Historical Support Available to Each Candidate

### TRAIN Retrieval Corpus (IDs 1–6)

| Candidate Key | Matching TRAIN Cases | Memory IDs | Template | TRAIN Support? |
|:---|:---:|:---|:---:|:---:|
| `orders:btree:(total_amount,customer_id)` | **0** | — | None (composite never appeared in TRAIN) | ❌ |
| `orders:btree:(total_amount,)` | **3** | 4, 5, 6 | T2 (`total_amount >`) | ✅ |
| `orders:btree:(customer_id,)` | **3** | 1, 2, 3 | T1 (`customer_id = `) | ✅ |

### Policy B Support Analysis

Policy B (`select_similarity`) searches TRAIN cases whose `extract_case_key(h)` matches the
candidate key. It accumulates `sim_support[key] += compute_token_hash_similarity(query_text, h.query.text)`.

- **Composite `(total_amount, customer_id)`**: 0 TRAIN matches → `similarity_support = 0.0`
  - Score = `hypopg_cost_improvement + (alpha * 0.0) = 87.55`
- **`(total_amount)`**: 3 TRAIN matches (IDs 4, 5, 6)
  - Score = `53.70 + (alpha * accumulated_sim_T2)`
- **`(customer_id)`**: 3 TRAIN matches (IDs 1, 2, 3)
  - Score = `76.52 + (alpha * accumulated_sim_T1)`

**Policy B has eligible support for candidates 2 and 3. It has zero support for the composite.**

Whether Policy B changes the selection from Policy A depends on whether accumulated similarity
scores for `(total_amount)` or `(customer_id)` boost their composite scores above 87.55.
This must be computed pre-measurement and frozen before physical execution.

### Policy C Support Analysis

Policy C (`select_outcome_aware`) filters to cases where `provenance==measured`, `is_verified==True`,
`verification_state==verified_measured`. All 6 TRAIN cases satisfy this.

Policy C accumulates `outcome_support[key] += sim * delta` where `delta = (t_before - t_after) / t_before`.

- **Composite `(total_amount, customer_id)`**: 0 TRAIN matches → `outcome_support = 0.0`
  - Score = `87.55 + (beta * 0.0) = 87.55`
- **`(total_amount)`**: 3 verified measured TRAIN matches (IDs 4, 5, 6)
  - Contributes positive outcome_support (T2 cases showed dT% improvement)
  - Score = `53.70 + (beta * accumulated_outcome_T2)`
- **`(customer_id)`**: 3 verified measured TRAIN matches (IDs 1, 2, 3)
  - Contributes positive outcome_support (T1 cases showed dT% improvement)
  - Score = `76.52 + (beta * accumulated_outcome_T1)`

**Policy C has eligible verified-measured support for candidates 2 and 3. Zero for the composite.**

> [!NOTE]
> Policy C does NOT fall back for this case because verified measured cases exist in TRAIN that
> match candidates 2 and 3. `total_measured_matching > 0` is satisfied.

---

## 6. Policy Definitions

### Policy A — Planner-Only Baseline

- **Source:** `CandidateSelector.select_planner_only()`
- **Rule:** Select the unique candidate where `is_baseline == True`.
- **Historical memory used:** None (zero similarity scores, zero outcome scores).
- **Expected selection:** `cand_orders_total_amount_customer_id`
  (composite `(total_amount, customer_id)`, HypoPG 87.55%).
- **Tiebreaker:** Not applicable (exactly one baseline candidate).

### Policy B — Similarity-Based Selection

- **Source:** `CandidateSelector.select_similarity()`
- **Rule:** Rank by `composite_score = hypopg_cost_improvement + (alpha * similarity_support)`.
  Tiebreakers: (1) hypopg_cost_improvement, (2) is_baseline, (3) lexicographic candidate_id.
- **Historical memory used:** TRAIN cases IDs 1–6 (template-hash disjoint from T9).
- **Retrieval:** `compute_token_hash_similarity(query_text, h.query.text)` for each TRAIN case
  whose canonical key matches a candidate key.
- **Expected behavior:** The composite (score = 87.55) may or may not be overtaken by
  `(customer_id)` (base 76.52 + similarity boost) or `(total_amount)` (base 53.70 + similarity boost).
  **Selection must be computed and frozen pre-measurement.**
- **Fallback:** None expected (TRAIN cases match candidates 2 and 3).
- **Hyperparameter:** `alpha = 1.0` (locked from Phase 6D).

### Policy C — Outcome-Aware Selection

- **Source:** `CandidateSelector.select_outcome_aware()`
- **Rule:** Rank by `composite_score = hypopg_cost_improvement + (beta * outcome_support)`.
  Tiebreakers: (1) outcome_support, (2) hypopg_cost_improvement, (3) is_baseline, (4) lexicographic.
- **Historical memory used:** TRAIN verified measured cases IDs 1–6.
- **Outcome signal:** `delta = (t_before - t_after) / t_before` from each TRAIN case's
  `measured_outcome.before_runtime_ms` and `after_runtime_ms`.
- **Asymmetric penalty:** Regression contributions amplified by `lambda_reg = 1.5`.
- **Expected behavior:** Composite (base 87.55, zero outcome_support) may or may not be
  overtaken. **Selection must be computed and frozen pre-measurement.**
- **Fallback:** None expected (`total_measured_matching > 0` for candidates 2 and 3).
- **Hyperparameters:** `beta = 1.0`, `lambda_reg = 1.5` (locked from Phase 6D).

---

## 7. Oracle Definition

The oracle is defined as:

**The candidate from the eligible pool that achieves the maximum realized runtime improvement
percent (`runtime_improvement_percent = (t_before - t_after) / t_before * 100`) when physically
measured independently.**

### Oracle Protocol

1. After policy selections are **frozen and recorded**, physically create each of the 3 eligible
   candidate indexes independently (one at a time, with full teardown between each measurement).
2. For each candidate, run W=2 warmup queries then N=10 measured queries, recording median
   `t_before_ms` and `t_after_ms`.
3. The oracle candidate is the one achieving `max(runtime_improvement_percent)` across all 3.
4. Oracle determination occurs **after** policy selections are locked and **independently** of
   which candidate any policy selected.

### Oracle Independence

The oracle result is compared to policy selections post-hoc. It does NOT influence:
- Which candidate the policies selected (selections are frozen first)
- Parameter values (alpha, beta, lambda_reg are frozen before any measurement)
- The retrieval corpus (TRAIN IDs 1–6 only, frozen)

---

## 8. Selection-Before-Measurement Requirement

**This is a mandatory sequencing control.**

The experiment MUST execute in this order:

```
Step 1: Freeze hyperparameters (alpha=1.0, beta=1.0, lambda_reg=1.5)
Step 2: Load TRAIN cases (IDs 1–6 only)
Step 3: Compute policy selections for all three policies
Step 4: Write selection results to phase8_selection_results.json
Step 5: [CHECKPOINT] Verify selections are written and timestamped
Step 6: Begin physical measurement of all 3 eligible candidates
Step 7: Record oracle (max dT% candidate)
Step 8: Compare policy selections against oracle
```

**No physical measurement (CREATE INDEX, EXPLAIN ANALYZE, benchmarking) may occur before Step 5.**

The timestamp in `phase8_selection_results.json` must predate any `CREATE INDEX` execution.

---

## 9. Leakage Controls

### Template Isolation

The T9 template hash must be verified absent from:
- `optimization_memories` (IDs 1–14)
- TRAIN partition (T1, T2)
- DEV partition (T3, T5)
- Phase 6D TEST partition (T7, T8)

This is verified statically from the Phase 6C manifest (SHA-256 locked).

### TRAIN Retrieval Boundary

Policy B and C may only access TRAIN cases (IDs 1–6). DEV cases (IDs 7–9) and TEST cases
(IDs 10–14) are never passed to the CandidateSelector. This boundary is identical to
Phase 6D and Phase 7.

### No TEST-Case Outcome in TRAIN

The realized benchmark outcomes for the Phase 8 TEST case (T9) must never be written into
`optimization_memories` during the experiment. Memory count must remain 14 throughout.

### No Composite-Template Leakage via T3

T3 (DEV) has the key `orders:btree:(total_amount,customer_id)` as its primary candidate.
T3 is in DEV, not TRAIN. Therefore the composite candidate for T9 has **zero TRAIN support**
even though a composite candidate appeared in DEV. The DEV boundary is enforced.

---

## 10. Parameter-Locking Rules

The following hyperparameters are **frozen from Phase 6D** and must not be tuned on this case:

| Parameter | Frozen Value | Source |
|:---:|:---:|:---|
| `alpha` | `1.0` | `phase6d_experiment_manifest.json` |
| `beta` | `1.0` | `phase6d_experiment_manifest.json` |
| `lambda_reg` | `1.5` | `phase6d_experiment_manifest.json` |
| `seed` | `42` | Phase 6C partition design |
| Warmup runs (W) | `2` | Phase 7 manifest |
| Measured runs (N) | `10` | Phase 7 manifest |

**No tuning on T9 outcome is permitted.** If any parameter change is proposed, it must be
justified using TRAIN/DEV evidence only, frozen before physical measurement, and documented
as a separate parameter-update record — not a post-hoc adjustment.

---

## 11. Memory-Write Restrictions

| Memory Operation | Permitted? | Notes |
|:---|:---:|:---|
| Read `optimization_memories` IDs 1–6 for policy computation | ✅ | TRAIN retrieval |
| Read `optimization_memories` IDs 7–14 | ❌ | DEV/TEST isolation |
| Write new T9 outcome to `optimization_memories` | ❌ | Experiment is read-only |
| Modify any existing memory row | ❌ | Corpus is immutable |
| `optimization_memories` count at end of experiment | Must equal **14** | Post-run invariant |

---

## 12. Physical Cleanup Requirements

For each of the 3 candidates physically measured:

1. Create index `CREATE INDEX idx_autodba_p8_orders_<columns> ON orders (<columns>);`
2. Run warmup + measurement queries
3. **DROP INDEX immediately after measurement**, before the next candidate is created.
4. Verify `SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_p8_%'` = 0
   after each teardown.
5. Final verification: 0 residual `idx_autodba_p8_*` indexes after all 3 measurements complete.

---

## 13. Stopping Criteria

The Phase 8 experiment is complete when:

1. ✅ Policy selections (A, B, C) are frozen and written to `phase8_selection_results.json`
2. ✅ All 3 eligible candidates are physically measured (or blocked with documented reason)
3. ✅ Oracle is determined
4. ✅ Policy vs. oracle comparison is recorded
5. ✅ All `idx_autodba_p8_*` indexes are dropped
6. ✅ `optimization_memories` count = 14 (verified post-run)
7. ✅ `PHASE8_EXECUTION_REPORT.md` written
8. ✅ `phase8_measurements.json` written

### Early Stop Conditions

- If HypoPG validation fails for all 3 candidates: document and stop. Do not proceed to
  physical measurement.
- If any candidate's physical measurement produces a regression (dT% < 0): record result,
  do not re-run, do not adjust parameters.

---

## 14. Methodological Limitation

> [!WARNING]
> **This is currently ONE informative multi-candidate unseen-template case.**
>
> One case is **not sufficient** for a strong comparative conclusion about policy superiority.
> The Phase 8 experiment can demonstrate:
> - Whether policies B and C diverge from A (qualitative finding)
> - The direction of divergence (composite vs. single-column preference)
> - Whether the divergent selection achieves better/worse oracle outcome (single data point)
>
> It **cannot** support statistically significant claims about expected policy performance.
> Multiple independent cases with |C| ≥ 2 across diverse templates are required for that.
>
> This limitation must be explicitly stated in the Phase 8 Execution Report.

---

## 15. Expected Artifact Outputs

Upon completion of physical execution, the following artifacts must be created:

| Artifact | Path | Description |
|:---|:---|:---|
| Design document | `research/PHASE8_MULTI_CANDIDATE_DESIGN.md` | This file |
| Pre-execution audit | `research/PHASE8_PRE_EXECUTION_AUDIT.md` | Leakage/invariant audit |
| Experiment manifest | `research/phase8_experiment_manifest.json` | Frozen parameters & identity |
| Selection results | `research/phase8_selection_results.json` | Policy A/B/C selections (pre-measurement) |
| Measurements | `research/phase8_measurements.json` | Oracle benchmark results |
| Execution report | `research/PHASE8_EXECUTION_REPORT.md` | Full results and interpretation |
| Audit trail | `research/PHASE8_AUDIT.md` | Post-run invariant verification |

---

## 16. Readiness Status

**Status: DESIGN COMPLETE — AWAITING PRE-EXECUTION AUDIT SIGN-OFF**

Before physical execution begins:
- [ ] Template hash T9 computed and locked in manifest
- [ ] T9 hash verified absent from all existing partitions
- [ ] Policy selections computed and verified (dry-run)
- [ ] `phase8_experiment_manifest.json` finalized and SHA-256 recorded
- [ ] Physical execution script reviewed for cleanup correctness
