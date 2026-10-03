# Phase 7 — Candidate Support Matrix

**Date:** 2026-10-01  
**Status:** DESIGN ONLY — zero measurements performed  
**Source of predictions:** Static analysis of `candidate_selector.py`,
`intelligence_service.py`, `recommendation_engine.py`, and read-only
PostgreSQL introspection.

> [!IMPORTANT]
> All eligibility, TRAIN match, and exerciseability fields below are
> **design-time predictions**, not measured results. "Expected to pass HypoPG"
> means the prediction based on existing-index inspection and column
> cardinality reasoning. Actual eligibility is determined at execution time.

---

## TRAIN Candidate Key Inventory (frozen, read-only reference)

| TRAIN Key | Memory IDs | Measured ΔT% Values | Mean ΔT% |
| :--- | :---: | :--- | :---: |
| `orders:btree:customer_id` | 1, 2, 3 | 88.49%, 80.34%, 81.64% | **83.5%** |
| `orders:btree:total_amount` | 4, 5, 6 | 72.37%, 96.81%, 64.79% | **78.0%** |

No other candidate keys exist in TRAIN. Any template on `order_items`, or any
composite key on `orders`, has **zero TRAIN matches**.

---

## Per-Case Candidate Support Table

### Template TP-A — `orders WHERE total_amount > ? AND status = ?`

Canonical: `select * from orders where total_amount > ? and status = ?`  
Template hash: `815f3236a3ee1069f642...` (DISJOINT from T1–T8)

| Case | Candidate | Exact Key | TRAIN Matches | Measured History Available | Is Baseline (Phase 1) | Expected HypoPG Eligible | Expected Safety Eligible | Multi-Candidate? | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| CASE-TP-A-01 | `orders(total_amount, status)` | `orders:btree:total_amount,status` | **0** | None | ✅ Yes | ✅ Likely | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-A-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Yes | **✅ YES** |
| CASE-TP-A-01 | `orders(status)` | `orders:btree:status` | **0** | None | ❌ No | ⚠️ Uncertain (low cardinality) | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-A-02 | `orders(total_amount, status)` | `orders:btree:total_amount,status` | **0** | None | ✅ Yes | ✅ Likely | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-A-02 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Yes | **✅ YES** |
| CASE-TP-A-02 | `orders(status)` | `orders:btree:status` | **0** | None | ❌ No | ⚠️ Uncertain (low cardinality) | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-A-03 | `orders(total_amount, status)` | `orders:btree:total_amount,status` | **0** | None | ✅ Yes | ✅ Likely | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-A-03 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Yes | **✅ YES** |
| CASE-TP-A-03 | `orders(status)` | `orders:btree:status` | **0** | None | ❌ No | ⚠️ Uncertain (low cardinality) | ✅ Likely | Yes | N/A (no TRAIN match) |

---

### Template TP-D — `orders WHERE status = ? AND total_amount > ?`

Canonical: `select * from orders where status = ? and total_amount > ?`  
Template hash: `6e7c69115154e2049a4e...` (DISJOINT from T1–T8 and TP-A)

| Case | Candidate | Exact Key | TRAIN Matches | Measured History Available | Is Baseline (Phase 1) | Expected HypoPG Eligible | Expected Safety Eligible | Multi-Candidate? | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| CASE-TP-D-01 | `orders(status, total_amount)` | `orders:btree:status,total_amount` | **0** | None | ✅ Yes | ✅ Likely | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-D-01 | `orders(status)` | `orders:btree:status` | **0** | None | ❌ No | ⚠️ Uncertain (low cardinality) | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-D-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Yes | **✅ YES** |
| CASE-TP-D-02 | `orders(status, total_amount)` | `orders:btree:status,total_amount` | **0** | None | ✅ Yes | ✅ Likely | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-D-02 | `orders(status)` | `orders:btree:status` | **0** | None | ❌ No | ⚠️ Uncertain (low cardinality) | ✅ Likely | Yes | N/A (no TRAIN match) |
| CASE-TP-D-02 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Yes | **✅ YES** |

---

### Template TP-B — `orders WHERE order_date >= ? AND total_amount > ?` (supplementary)

Canonical: `select * from orders where order_date >= ? and total_amount > ?`  
Template hash: `f6d14dd0fecf32e32b6e...` (DISJOINT from all others)

> **Low confidence:** `idx_orders_order_date` already exists and is predicted
> to cause HypoPG NO_IMPROVEMENT or SafetyAssessor rejection for `order_date`
> candidates. Effective pool may reduce to 1 candidate.

| Case | Candidate | Exact Key | TRAIN Matches | Measured History Available | Is Baseline (Phase 1) | Expected HypoPG Eligible | Expected Safety Eligible | Multi-Candidate? | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| CASE-TP-B-01 | `orders(order_date, total_amount)` | `orders:btree:order_date,total_amount` | **0** | None | ✅ Yes | ⚠️ Uncertain (existing order_date index) | ⚠️ Uncertain | Conditional | N/A |
| CASE-TP-B-01 | `orders(order_date)` | `orders:btree:order_date` | **0** | None | ❌ No | ❌ Likely NO_IMPROVEMENT (existing idx_orders_order_date) | ❌ Likely blocked | Conditional | ❌ NO |
| CASE-TP-B-01 | `orders(total_amount)` | `orders:btree:total_amount` | **3** (IDs 4,5,6) | 72.37%, 96.81%, 64.79% | ❌ No | ✅ Likely | ✅ Likely | Conditional | ⚠️ Only if pool ≥ 2 |

---

### Excluded Templates (for completeness)

#### TP-C — `order_items WHERE unit_price > ?`

| Case | Candidate | Exact Key | TRAIN Matches | Multi-Candidate? | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :---: | :---: |
| (excluded) | `order_items(unit_price)` | `order_items:btree:unit_price` | **0** | No (single candidate) | ❌ NO — guaranteed fallback |

**Exclusion reason:** Single candidate, no TRAIN match, zero differentiation opportunity.

#### TP-E — `order_items WHERE product_id = ? AND quantity > ?`

| Case | Candidate | Exact Key | TRAIN Matches | Expected HypoPG Eligible | Expected B/C Exerciseable? |
| :--- | :--- | :--- | :---: | :---: | :---: |
| (excluded) | `order_items(product_id, quantity)` | `order_items:btree:product_id,quantity` | **0** | ⚠️ Uncertain (existing product_id index) | ❌ NO |
| (excluded) | `order_items(product_id)` | `order_items:btree:product_id` | **0** | ❌ Likely blocked (equivalent index exists) | ❌ NO |
| (excluded) | `order_items(quantity)` | `order_items:btree:quantity` | **0** | ✅ Likely | ❌ NO (no TRAIN match) |

**Exclusion reason:** No TRAIN key matches; multi-candidate pool uncertain due to existing product_id index.

---

## Exerciseability Summary

| Case | Template | Multi-Candidate (predicted) | TRAIN-Matched Candidate | B/C Exerciseable | Confidence |
| :--- | :---: | :---: | :--- | :---: | :---: |
| CASE-TP-A-01 | TP-A | ✅ Yes (2–3) | `orders(total_amount)` — IDs 4,5,6 | **✅ YES** | High |
| CASE-TP-A-02 | TP-A | ✅ Yes (2–3) | `orders(total_amount)` — IDs 4,5,6 | **✅ YES** | High |
| CASE-TP-A-03 | TP-A | ✅ Yes (2–3) | `orders(total_amount)` — IDs 4,5,6 | **✅ YES** | High |
| CASE-TP-D-01 | TP-D | ✅ Yes (2–3) | `orders(total_amount)` — IDs 4,5,6 | **✅ YES** | High |
| CASE-TP-D-02 | TP-D | ✅ Yes (2–3) | `orders(total_amount)` — IDs 4,5,6 | **✅ YES** | High |
| CASE-TP-B-01 | TP-B | ⚠️ Conditional (1–3) | `orders(total_amount)` — IDs 4,5,6 | **⚠️ Conditional** | Low |

**Primary corpus exerciseability rate: 5/5 (100%) — high confidence**  
**With supplementary: 5/6 primary + 1 conditional**

---

## Policy Selection Prediction Narrative

### What Policy A does on TP-A / TP-D cases

Policy A selects the Phase 1 baseline candidate — the composite
`orders(total_amount, status)` or `orders(status, total_amount)` depending on
template. This is because `is_baseline=True` is assigned to the all-columns
candidate in `_evaluate_candidates` and Policy A simply returns it.

### What Policy B does on TP-A / TP-D cases

Policy B computes:

```
composite_score(candidate) = hypopg_cost_improvement + α × similarity_support
```

Where `similarity_support` = sum of token-hash cosine similarities to TRAIN
queries whose candidate key matches this candidate's key.

- `orders(total_amount, status)` — 0 TRAIN matches → similarity_support = 0.0
- `orders(total_amount)` — 3 TRAIN matches (IDs 4,5,6) → similarity_support > 0
- `orders(status)` — 0 TRAIN matches → similarity_support = 0.0

The TRAIN queries for `total_amount` (`SELECT * FROM orders WHERE total_amount > X`)
will have non-trivial token-hash similarity to the test query
(`SELECT * FROM orders WHERE total_amount > Y AND status = Z`) because they
share tokens: `select`, `from`, `orders`, `where`, `total_amount`.

**Predicted outcome:** `orders(total_amount)` accumulates the highest composite
score IF its base HypoPG cost improvement is competitive with the composite's.
Policy B is predicted to **diverge from Policy A** by selecting
`orders(total_amount)`.

### What Policy C does on TP-A / TP-D cases

Policy C computes:

```
composite_score(candidate) = hypopg_cost_improvement + β × outcome_support
```

Where `outcome_support` = sum of `similarity(test_query, train_query) × delta`
for all TRAIN matches of this candidate's key.

- `orders(total_amount)` → 3 TRAIN matches with deltas [72.37%, 96.81%, 64.79%]
  → large positive outcome_support
- All other candidates → 0 outcome_support

**Predicted outcome:** `orders(total_amount)` dominates the composite score
(outcome_support contribution ≈ 0.5–0.8 × 78% mean = ~0.40–0.62). Policy C
is predicted to **diverge from Policy A** and agree with Policy B in selecting
`orders(total_amount)`.

### What the Oracle determines

The empirical oracle benchmarks ALL eligible candidates physically. The oracle
will reveal whether `orders(total_amount)` or `orders(total_amount, status)`
achieves higher measured ΔT% on this specific query. This is not predictable
from TRAIN evidence alone — it is an empirical question.

**The experiment is scientifically honest:** If the composite beats
`total_amount` alone, then B/C incur regret despite using historical evidence.
If `total_amount` alone wins, B/C outperform A. Either outcome is a valid
finding about the value of historical candidate evidence.

---

## Key Question Answer

> **"Will this proposed corpus actually give Policies B and/or C a legitimate
> opportunity to use historical evidence on an unseen query template, while
> preserving the leakage boundary?"**

**Yes — for CASE-TP-A-01, CASE-TP-A-02, CASE-TP-A-03, CASE-TP-D-01, CASE-TP-D-02.**

Specifically:
- Templates TP-A and TP-D are genuinely unseen (disjoint template hashes from T1–T8).
- Candidate `orders:btree:total_amount` appears in both the test query's Phase 1
  candidate pool AND the TRAIN history (IDs 4, 5, 6) with measured deltas.
- The Phase 1 baseline candidate (`orders:btree:total_amount,status` or
  `orders:btree:status,total_amount`) has **zero TRAIN support**, creating a
  genuine asymmetry between the baseline and the TRAIN-supported non-baseline.
- Policies B and C will process non-zero evidence for one candidate and zero
  evidence for the others, and their ranking will reflect that asymmetry.
- The leakage boundary is preserved: retrieval is strictly frozen to IDs 1–6.
- Phase 7 outcomes will not be persisted to `optimization_memories`.
