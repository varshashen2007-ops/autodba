# Phase 7 — Targeted Measured-Corpus Expansion Design Audit

**Date:** 2026-10-01  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Status:** DESIGN ONLY — zero measurements performed, zero database mutations

---

## A. Objective

Design additional measured cases that give Policies B and C a genuine
opportunity to use historical candidate-key evidence on **previously unseen**
query templates, while preserving the locked Phase 6C partition and all
leakage boundaries.

The core test question for Phase 7 is:

> "When a test query shares a candidate key with TRAIN history but belongs to a
> genuinely unseen template, do Policies B and C use that evidence to rank
> candidates differently from Policy A, and does that ranking produce a better
> or worse measured outcome than the baseline?"

---

## B. Phase 6D Limitation

Phase 6D was methodologically clean but failed to exercise the retrieval
mechanism because:

1. **Template T7** (`order_items(quantity, unit_price)`) — TRAIN covers only
   `orders`-table candidates. Zero candidate key matches → 100% fallback rate.

2. **Template T8** (`orders(customer_id, status)`) — Only one eligible
   candidate existed (`orders(customer_id)`), meaning even with TRAIN matches
   no divergence was possible.

**Root cause:** The Phase 6C TRAIN partition covers only two relations
(`orders`) and two candidate keys (`customer_id`, `total_amount`). Any test
template on `order_items` necessarily has zero TRAIN support under exact key
matching. Any `orders` template with only one eligible candidate produces
trivial agreement.

**Required fix:** Design Phase 7 test templates that:
(a) target `orders` (where TRAIN evidence exists), AND  
(b) generate **multiple** eligible candidates including `orders(total_amount)`
or `orders(customer_id)`, AND  
(c) have a genuinely new canonical template hash (no collision with T1–T8).

---

## C. Existing TRAIN Candidate-Key Inventory

TRAIN partition = Memory IDs 1–6 only. Verified from live `optimization_memories`.

| TRAIN Key (canonical) | Memory IDs | T_before (ms) | T_after (ms) | Measured ΔT% |
| :--- | :---: | :--- | :--- | :--- |
| `orders:btree:customer_id` | 1, 2, 3 | 0.2858 / 0.1648 / 0.1487 | 0.0329 / 0.0324 / 0.0273 | 88.49% / 80.34% / 81.64% |
| `orders:btree:total_amount` | 4, 5, 6 | 0.3463 / 0.3014 / 0.3238 | 0.0957 / 0.0096 / 0.1140 | 72.37% / 96.81% / 64.79% |

**Mean TRAIN delta for `customer_id`:** ~83.5%  
**Mean TRAIN delta for `total_amount`:** ~78.0%

**Exact matching rule (from `candidate_selector.py` lines 36–51):**
```python
canonical_candidate_key(table, index_method, columns)
= (table.lower(), method.lower(), tuple(col.lower() for col in columns))
```

Only the exact tuple `(orders, btree, (customer_id,))` or
`(orders, btree, (total_amount,))` triggers a match. Composite or reversed
tuples do NOT match.

---

## D. Candidate New Templates Considered

The following five candidate templates were evaluated. All were verified to be
DISJOINT from existing template hashes T1–T8 (confirmed by SHA-256 comparison).

### Schema snapshot used for this analysis

**`orders`** (5,000 rows):
- Columns: `id`, `customer_id`, `total_amount`, `status`, `order_date`
- Existing indexes: `orders_pkey (id)`, `idx_orders_order_date (order_date)`
- No existing index on `customer_id`, `total_amount`, or `status`

**`order_items`** (15,000 rows):
- Columns: `id`, `order_id`, `product_id`, `quantity`, `unit_price`
- Existing indexes: `order_items_pkey (id)`, `idx_order_items_order_id (order_id)`,
  `idx_order_items_product_id (product_id)`
- No existing index on `quantity`, `unit_price`

### TP-A: `orders WHERE total_amount > ? AND status = ?`

- **Canonical:** `select * from orders where total_amount > ? and status = ?`
- **Template hash prefix:** `815f3236a3ee1069f642...`
- **DISJOINT from T1–T8:** ✅
- **Phase 1 candidate pool (predicted):**
  1. `orders:btree:total_amount,status` — baseline (multi-col, all extracted cols)
  2. `orders:btree:total_amount` — single-col
  3. `orders:btree:status` — single-col
- **TRAIN matches:** `orders:btree:total_amount` → IDs 4, 5, 6 ✅
- **Multi-candidate:** Yes (3 candidates predicted)
- **B/C exerciseable:** ✅ — `total_amount` candidate has TRAIN support; composite and `status` do not

### TP-B: `orders WHERE order_date >= ? AND total_amount > ?`

- **Canonical:** `select * from orders where order_date >= ? and total_amount > ?`
- **Template hash prefix:** `f6d14dd0fecf32e32b6e...`
- **DISJOINT from T1–T8:** ✅
- **Phase 1 candidate pool (predicted):**
  1. `orders:btree:order_date,total_amount` — baseline (multi-col)
  2. `orders:btree:order_date` — single-col
  3. `orders:btree:total_amount` — single-col
- **Important caveat:** `idx_orders_order_date` already exists. HypoPG
  simulation for `order_date` alone may yield NO_IMPROVEMENT or REGRESSION
  since the planner can use the existing index. SafetyAssessor may exclude
  `order_date` single-col if it detects an equivalent existing index.
  Candidate pool may reduce to 2 or fewer eligible candidates after
  HypoPG/safety filtering.
- **TRAIN matches:** `orders:btree:total_amount` → IDs 4, 5, 6 ✅ (if eligible)
- **Multi-candidate:** Uncertain — depends on HypoPG/safety outcome for `order_date` candidates
- **B/C exerciseable:** Conditionally ✅ — only if `order_date`-based candidates
  are not all rejected by HypoPG/safety

### TP-C: `order_items WHERE unit_price > ?`

- **Canonical:** `select * from order_items where unit_price > ?`
- **Template hash prefix:** `052580654221f0d4600f...`
- **DISJOINT from T1–T8:** ✅
- **Phase 1 candidate pool (predicted):**
  1. `order_items:btree:unit_price` — baseline (single col = baseline)
- **TRAIN matches:** None (TRAIN covers only `orders`)
- **Multi-candidate:** No (single col = single candidate)
- **B/C exerciseable:** ❌ — fallback guaranteed

### TP-D: `orders WHERE status = ? AND total_amount > ?`

- **Canonical:** `select * from orders where status = ? and total_amount > ?`
- **Template hash prefix:** `6e7c69115154e2049a4e...`
- **DISJOINT from T1–T8:** ✅
- **Note:** TP-D and TP-A extract the **same two columns** (`status`, `total_amount`)
  from different predicate orderings. They have different template hashes but
  produce **the same Phase 1 candidate pool**.
- **Phase 1 candidate pool (predicted):**
  1. `orders:btree:status,total_amount` — baseline
  2. `orders:btree:status` — single-col
  3. `orders:btree:total_amount` — single-col (TRAIN matched)
- **TRAIN matches:** `orders:btree:total_amount` → IDs 4, 5, 6 ✅
- **Multi-candidate:** Yes (3 candidates predicted)
- **B/C exerciseable:** ✅

### TP-E: `order_items WHERE product_id = ? AND quantity > ?`

- **Canonical:** `select * from order_items where product_id = ? and quantity > ?`
- **Template hash prefix:** `c00177ed84e8c077651c...`
- **DISJOINT from T1–T8:** ✅
- **Important caveat:** `idx_order_items_product_id` already exists. Safety
  assessor or HypoPG is likely to reject/exclude `product_id` single-col
  candidate. `quantity` single-col has no TRAIN match (TRAIN is `orders`-only).
- **TRAIN matches:** None
- **Multi-candidate:** Uncertain (depends on HypoPG/safety for `product_id`)
- **B/C exerciseable:** ❌ — no TRAIN key matches

---

## E. Detailed Candidate-Case Table

Proposed cases use the **two exerciseable templates** (TP-A and TP-D), which
maximize the opportunity for B/C retrieval to operate. TP-B is retained as an
exploratory candidate with lower confidence on multi-candidate outcome.

| Case ID | Template | SQL | Table | Predicted Candidate Pool | Pool Size | TRAIN Matches | B/C Exerciseable? |
| :--- | :---: | :--- | :---: | :--- | :---: | :---: | :---: |
| CASE-TP-A-01 | TP-A | `orders WHERE total_amount > 200.00 AND status = 'PENDING'` | orders | `(total_amount,status)`, `(total_amount)`, `(status)` | 3 (predicted) | `(total_amount)` — IDs 4,5,6 | ✅ |
| CASE-TP-A-02 | TP-A | `orders WHERE total_amount > 350.00 AND status = 'SHIPPED'` | orders | `(total_amount,status)`, `(total_amount)`, `(status)` | 3 (predicted) | `(total_amount)` — IDs 4,5,6 | ✅ |
| CASE-TP-A-03 | TP-A | `orders WHERE total_amount > 150.00 AND status = 'COMPLETED'` | orders | `(total_amount,status)`, `(total_amount)`, `(status)` | 3 (predicted) | `(total_amount)` — IDs 4,5,6 | ✅ |
| CASE-TP-D-01 | TP-D | `orders WHERE status = 'CANCELLED' AND total_amount > 250.00` | orders | `(status,total_amount)`, `(status)`, `(total_amount)` | 3 (predicted) | `(total_amount)` — IDs 4,5,6 | ✅ |
| CASE-TP-D-02 | TP-D | `orders WHERE status = 'PROCESSING' AND total_amount > 100.00` | orders | `(status,total_amount)`, `(status)`, `(total_amount)` | 3 (predicted) | `(total_amount)` — IDs 4,5,6 | ✅ |
| CASE-TP-B-01 | TP-B | `orders WHERE order_date >= '2025-02-15' AND total_amount > 200.00` | orders | `(order_date,total_amount)`, `(order_date)`, `(total_amount)` — uncertain eligibility | 1–3 (predicted) | `(total_amount)` — IDs 4,5,6 | ⚠️ Conditional |

> **Prediction confidence note:** Column counts above are predicted from the
> Phase 1 `_evaluate_candidates` logic and RecommendationEngine
> `extract_candidate_columns` regex. The actual safety-eligible pool is
> determined at execution time by HypoPGValidatorService and SafetyAssessor.
> TP-B is labeled conditional because `idx_orders_order_date` may cause the
> `order_date` candidates to be rejected by HypoPG (no improvement vs existing
> index), reducing the pool to `(total_amount)` only — which would be a single
> candidate and produce trivial agreement.

---

## F. Expected Historical Support Matrix

For each proposed case, the exact TRAIN candidate key evidence available to
Policies B and C at selection time:

| Case | Candidate | Exact Key | TRAIN Matches | Measured ΔT% Available | Multi-Candidate? | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: |
| CASE-TP-A-01 | `orders(total_amount,status)` | `orders:btree:total_amount,status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-A-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Yes | **✅ YES** |
| CASE-TP-A-01 | `orders(status)` | `orders:btree:status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-A-02 | `orders(total_amount,status)` | `orders:btree:total_amount,status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-A-02 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Yes | **✅ YES** |
| CASE-TP-A-02 | `orders(status)` | `orders:btree:status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-A-03 | `orders(total_amount,status)` | `orders:btree:total_amount,status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-A-03 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Yes | **✅ YES** |
| CASE-TP-A-03 | `orders(status)` | `orders:btree:status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-D-01 | `orders(status,total_amount)` | `orders:btree:status,total_amount` | 0 | None | Yes | N/A (no match) |
| CASE-TP-D-01 | `orders(status)` | `orders:btree:status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-D-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Yes | **✅ YES** |
| CASE-TP-D-02 | `orders(status,total_amount)` | `orders:btree:status,total_amount` | 0 | None | Yes | N/A (no match) |
| CASE-TP-D-02 | `orders(status)` | `orders:btree:status` | 0 | None | Yes | N/A (no match) |
| CASE-TP-D-02 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Yes | **✅ YES** |
| CASE-TP-B-01 | `orders(order_date,total_amount)` | `orders:btree:order_date,total_amount` | 0 | None | Conditional | N/A (no match) |
| CASE-TP-B-01 | `orders(order_date)` | `orders:btree:order_date` | 0 | None | Conditional | ❌ (no match; may be rejected by HypoPG) |
| CASE-TP-B-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | Conditional | ⚠️ Only if pool is ≥ 2 eligible |

---

## G. Expected A/B/C Exerciseability Analysis

### Mechanism when B/C are exerciseable (TP-A, TP-D cases)

For a case like CASE-TP-A-01 (`orders WHERE total_amount > 200.00 AND status = 'PENDING'`):

1. **Policy A** selects the Phase 1 baseline candidate = `orders(total_amount,status)` —
   the composite multi-column index (all extracted columns = baseline by design
   in `_evaluate_candidates`).

2. **Policy B** computes token-hash similarity between the test query and each
   of the 6 TRAIN queries. All 6 are on `orders` with single-column predicates.
   Similarity to a `total_amount > ?` query will be non-trivial. The composite
   key `(total_amount,status)` has zero TRAIN matches. The `(total_amount)` key
   accumulates non-zero similarity support. The `(status)` key has zero support.
   Score = `hypopg_cost_improvement + α * similarity_support`.
   Result: Policy B likely selects `orders(total_amount)` over the composite,
   **diverging from Policy A**.

3. **Policy C** computes outcome support: the `(total_amount)` candidate has
   3 TRAIN matches with delta × similarity contributions of ~78% mean delta.
   The composite and `(status)` candidates have zero outcome support.
   Result: Policy C likely selects `orders(total_amount)`, **diverging from Policy A**.

**Expected divergence:** On all 5 TP-A / TP-D cases, Policies B and C are
expected to select `orders(total_amount)` while Policy A selects
`orders(total_amount,status)`. This creates a genuine three-way evaluation
opportunity where the oracle will determine which selection was actually better.

> **Important disclaimer:** This is a DESIGN PREDICTION only. The actual
> selection depends on the precise HypoPG cost improvement values for each
> candidate at runtime, and the similarity computation may produce unexpected
> tie-breaking behavior. The oracle is determined independently by physical
> benchmarking of all candidates.

### TP-B risk assessment

TP-B contains `order_date` which already has `idx_orders_order_date`. 
Predicted behavior:
- `orders:btree:order_date` — HypoPG is likely to show NO_IMPROVEMENT or
  REGRESSION (planner can already use `idx_orders_order_date`). SafetyAssessor
  may flag it as REJECTED.
- If both `order_date`-related candidates are rejected, pool = {`total_amount`}
  → single candidate → trivial agreement → B/C immediately fall back.
- TP-B is therefore labeled **low confidence** for multi-candidate eligibility.
  It is included as a supplementary case only.

---

## H. Leakage Analysis

### Phase 7 leakage boundary design

```
FROZEN TRAIN (IDs 1–6, templates T1/T2, orders only)
              ↓ retrieval boundary
Phase 7 TEST queries (TP-A, TP-D templates — new hash, orders table)
              ↓ offline policy selection (before benchmarking)
A/B/C selection locked in artifact
              ↓ physical candidate benchmarking
Independent oracle (exhaustive per-candidate physical measurement)
              ↓ NOT persisted to optimization_memories
Research artifact only
```

### Invariants preserved

| Invariant | Status |
| :--- | :---: |
| Phase 6C partition manifest unchanged | ✅ |
| Frozen TRAIN = IDs 1–6 only | ✅ |
| Phase 7 test outcomes NOT inserted into `optimization_memories` | ✅ (by design) |
| DEV partition (IDs 7–9) not used for Phase 7 retrieval | ✅ |
| Phase 6D TEST outcomes (IDs 10–14) not used for retrieval | ✅ |
| Phase 7 template hashes disjoint from T1–T8 | ✅ (verified) |
| Phase 7 templates disjoint from each other | ✅ (TP-A ≠ TP-D, different hashes) |

### Leakage risk: TP-A vs TP-D template similarity

TP-A and TP-D differ in predicate column order (`total_amount > ? AND status = ?`
vs `status = ? AND total_amount > ?`). They canonicalize to **different hashes**
and are therefore separate templates. However, they extract the **same candidate
pool** because `extract_candidate_columns` is order-insensitive in the filter
regex. This is not leakage — it is an accurate reflection of the system design.

If both are measured, they form a **within-Phase-7 mini-leakage risk** if
results from one inform interpretation of the other. They should be treated as
separate test cases from different templates, evaluated independently.

---

## I. Database-State Assumptions

All predictions are made under these observed database conditions:

| Assumption | Verified Value |
| :--- | :--- |
| `orders` row count | 5,000 |
| `order_items` row count | 15,000 |
| `status` distinct values | 5 (cancelled/completed/pending/processing/shipped), 1,000 each |
| `total_amount` range | 25.50 – 474.50, mean ≈ 249.93 |
| `idx_orders_order_date` exists | ✅ yes |
| `idx_order_items_order_id` exists | ✅ yes |
| `idx_order_items_product_id` exists | ✅ yes |
| No `idx_autodba_*` residual indexes | ✅ confirmed (count = 0) |
| `optimization_memories` count | 14 exactly |

Proposed filter parameter values were chosen to ensure selectivity > ~10% to
produce a meaningful sequential scan (not returning 0 rows), while avoiding
ranges that approach full table scans (which may cause HypoPG NO_IMPROVEMENT).

---

## J. Risks and Limitations

### Risk 1: HypoPG may reject `status` as an index candidate

`orders.status` is a low-cardinality column (5 distinct values, uniform
distribution, 1,000 rows each). HypoPG may determine that an index on `status`
alone provides NO_IMPROVEMENT because the planner prefers a sequential scan for
~20% selectivity predicates. If so, `orders(status)` is excluded from the
eligible pool. The effective pool becomes `{(total_amount,status), (total_amount)}`,
still multi-candidate.

### Risk 2: Composite `(total_amount,status)` may not pass HypoPG for all parameter values

For low selectivity parameter combinations (e.g., `total_amount > 50` returning
most rows), HypoPG may flag NO_IMPROVEMENT for the composite as well. This
reduces pool to single candidate and produces trivial agreement. Proposed
parameter values (>150, >200, >250, >350) are intended to achieve moderate
selectivity (15–40% of 5,000 rows).

### Risk 3: `orders(status)` equivalence collision

`orders(status)` as a candidate is NEW — no equivalent physical index exists.
SafetyAssessor should pass it. However, it is genuinely unlikely to outperform
`orders(total_amount)` empirically given the low cardinality of `status`.
This makes the oracle likely to prefer `total_amount` or the composite — which
is the scientifically honest finding.

### Risk 4: Policy B/C may not actually diverge from A if HypoPG scores dominate

Policy B scoring: `hypopg_cost_improvement + α * similarity_support`

If the composite `(total_amount,status)` has a substantially higher HypoPG
cost improvement than `(total_amount)`, then even with non-zero similarity
support for `(total_amount)`, the composite score may dominate. In that case
B and C may agree with A despite having TRAIN evidence. This is a correct,
honest outcome — not a failure of the design.

### Risk 5: TP-A and TP-D share identical TRAIN evidence

Both templates produce `orders(total_amount)` as the TRAIN-matched candidate
with the same 3 TRAIN cases (IDs 4,5,6). The similarity scores will differ
(different query text → different token hash similarity), but the outcome
support is the same. Treating them as independent cases with the same TRAIN
history is methodologically honest.

### Risk 6: Buffer cache effects

`orders` has 5,000 rows (~45 shared blocks). Shared buffers may retain cached
pages across candidates. `W=2` warmup mitigates cold-start but does not reset
shared buffers. This is a pre-declared limitation (from Phase 6 design).

---

## K. Recommended Phase 7 Corpus

Based on the analysis above, the recommended Phase 7 corpus is:

### Primary corpus (high confidence, recommended)

| Case ID | Template | SQL | Role | Rationale |
| :--- | :---: | :--- | :---: | :--- |
| CASE-TP-A-01 | TP-A | `SELECT * FROM orders WHERE total_amount > 200.00 AND status = 'PENDING'` | TEST | Multi-candidate; TRAIN support on `(total_amount)` |
| CASE-TP-A-02 | TP-A | `SELECT * FROM orders WHERE total_amount > 350.00 AND status = 'SHIPPED'` | TEST | Same template, different params; tests consistency |
| CASE-TP-A-03 | TP-A | `SELECT * FROM orders WHERE total_amount > 150.00 AND status = 'COMPLETED'` | TEST | Lower threshold; higher selectivity variation |
| CASE-TP-D-01 | TP-D | `SELECT * FROM orders WHERE status = 'CANCELLED' AND total_amount > 250.00` | TEST | Different template hash, same candidate pool as TP-A |
| CASE-TP-D-02 | TP-D | `SELECT * FROM orders WHERE status = 'PROCESSING' AND total_amount > 100.00` | TEST | Lower threshold; tests low-selectivity edge |

### Supplementary case (conditional, lower confidence)

| Case ID | Template | SQL | Role | Rationale |
| :--- | :---: | :--- | :---: | :--- |
| CASE-TP-B-01 | TP-B | `SELECT * FROM orders WHERE order_date >= '2025-02-15' AND total_amount > 200.00` | TEST | Multi-candidate only if `order_date` candidates survive HypoPG/safety |

### Phase 7 partition design

Phase 7 is a **new, independent evaluation corpus** evaluated against the same
frozen TRAIN (IDs 1–6). It is NOT an extension of Phase 6C.

- **Phase 7 TRAIN retrieval corpus:** Frozen TRAIN (Memory IDs 1–6) — unchanged.
- **Phase 7 TEST partition:** All 5 primary cases + optionally CASE-TP-B-01.
- **No Phase 7 DEV partition** is proposed; corpus is small enough for direct
  TEST evaluation.
- Phase 7 outcomes are NEVER persisted to `optimization_memories`.
- Phase 7 manifest has its own SHA-256 lock separate from Phase 6C.

### Exclusions and rationale

| Excluded Template | Reason |
| :--- | :--- |
| TP-C (`order_items WHERE unit_price > ?`) | Single candidate, no TRAIN match — guaranteed fallback, no experiment value |
| TP-E (`order_items WHERE product_id = ? AND quantity > ?`) | No TRAIN matches (TRAIN is orders-only); `product_id` has existing index |

---

## L. Explicit Statement — No Measurements Performed

**No benchmarks were executed.**  
**No indexes were created or dropped.**  
**No `optimization_memories` rows were inserted, updated, or deleted.**  
**No Phase 6C partition invariants were modified.**  
**The partition manifest SHA-256 `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27` remains intact.**

All predictions in this document are design-time predictions derived from:
- Static analysis of `research/candidate_selector.py`
- Static analysis of `autodba-main/backend/app/services/intelligence_service.py`
- Static analysis of `autodba-main/backend/app/services/recommendation_engine.py`
- Live read-only database introspection (schema, row counts, existing indexes)
- Live read-only `optimization_memories` inspection

None of these predictions constitute measured eligibility or measured outcomes.

---

## Final Verdict

# **A. PHASE 7 CORPUS DESIGN READY FOR EXECUTION**

**Reason:** Templates TP-A (3 cases) and TP-D (2 cases) are:
1. Genuinely unseen relative to locked TRAIN (disjoint template hashes)
2. Targeted at `orders` table — where TRAIN history (`orders:btree:total_amount`, IDs 4–6) exists
3. Predicted to generate ≥2 eligible candidates each
4. Structured so that exactly one candidate (`orders(total_amount)`) has
   substantial TRAIN measured support while the baseline (`orders(total_amount,status)`) does not
5. Leakage-safe — Phase 7 outcomes stay in research artifacts only
6. Realistic for the AutoDBA workload (standard filter queries on the orders table)

This gives Policies B and C a legitimate opportunity to use historical evidence
and potentially diverge from Policy A on a genuinely unseen template, which
is the exact experimental gap that Phase 6D exposed.
