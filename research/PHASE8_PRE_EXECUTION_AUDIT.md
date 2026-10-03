# Phase 8: Pre-Execution Audit

**Date:** 2026-10-03  
**Status:** AUDIT COMPLETE — ELIGIBLE FOR PHYSICAL EXECUTION  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Hash verification script:** `research/scratch/phase8_hash_verify.py` (read-only, stdlib only)

---

## Section A — Canonicalization Audit

### A1. How canonicalize_sql Treats `>` vs `>=`

**Finding: `>` and `>=` produce distinct canonical templates.**

From `research/case_schema.py` lines 89–97, step 8 of `canonicalize_sql()`:

```python
# Step 8a: Normalize spacing around punctuation (matches single chars =, <, >)
s = re.sub(r"\s*([,()=<>])\s*", r" \1 ", s)
# Step 8b: Re-join <> (not equals)
s = re.sub(r"<\s*>", "<>", s)
# Step 8c: Re-join <=
s = re.sub(r"<\s*=", "<=", s)
# Step 8d: Re-join >=
s = re.sub(r">\s*=", ">=", s)
# Step 8e: Re-join !=
s = re.sub(r"!\s*=", "!=", s)
```

Step 8a separates `>=` into `> =`. Steps 8d repairs `> =` back to `>=`.
The final token `>=` is **preserved** in the canonical form — it is **not collapsed to `>`**.

| Input Operator | After step 8a | After step 8d | Final token |
|:---:|:---:|:---:|:---:|
| `>` | `>` (with spaces) | unchanged | `>` |
| `>=` | `> =` (split) | `>=` (rejoined) | `>=` |

**Conclusion:** `>` and `>=` generate **different canonical templates** and therefore **different SHA-256 hashes**.

---

## Section B — Template Hash Verification

### B1. Computed Hashes (via read-only `phase8_hash_verify.py`)

| Template ID | Canonical Form | SHA-256 Hash | Status |
|:---:|:---|:---|:---:|
| **T9** (Phase 8 new) | `select * from orders where customer_id = ? and total_amount >= ?` | `8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343` | 🆕 **NEW** |
| **T3** (DEV, existing) | `select * from orders where customer_id = ? and total_amount > ?` | `30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2` | Locked |

**T9 ≠ T3:** The two hashes differ. The `>=` template is structurally distinct from the `>` template.

### B2. Phase 6C Locked Hash Cross-Check

| Template | Locked Hash (Phase 6C manifest) | Computed Hash | Match? |
|:---:|:---|:---|:---:|
| T1 | `036cb1ede04b97e1c6f74baa1d4fdce5cbfb6cca2ad7c64a8018d1c4f608a636` | `036cb1ede04b97e1c6f74baa1d4fdce5cbfb6cca2ad7c64a8018d1c4f608a636` | ✅ |
| T2 | `f5bbbbeea30650c2c997aeadc2230f1b37fe979559019aba0304bf15730e563c` | `f5bbbbeea30650c2c997aeadc2230f1b37fe979559019aba0304bf15730e563c` | ✅ |
| T3 | `30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2` | `30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2` | ✅ |

**The `canonicalize_sql` function in this environment produces the same hashes as the locked Phase 6C manifest.** The implementation is stable.

---

## Section C — Candidate Key Canonicalization

### C1. Exact Candidate Keys

From `canonical_candidate_key()` in `research/candidate_selector.py` lines 36–51:

```python
(table.strip().lower(), index_method.strip().lower(), tuple(c.strip().lower() for c in columns))
```

| Candidate | Input | Canonical Tuple | String Form |
|:---|:---|:---|:---|
| Composite (baseline) | table=`orders`, cols=`[total_amount, customer_id]`, method=`btree` | `("orders", "btree", ("total_amount", "customer_id"))` | `orders:btree:(total_amount,customer_id)` |
| Single total_amount | table=`orders`, cols=`[total_amount]`, method=`btree` | `("orders", "btree", ("total_amount",))` | `orders:btree:(total_amount,)` |
| Single customer_id | table=`orders`, cols=`[customer_id]`, method=`btree` | `("orders", "btree", ("customer_id",))` | `orders:btree:(customer_id,)` |

### C2. Column Ordering Preservation

The B-tree column ordering in the composite candidate is `(total_amount, customer_id)` — **not** `(customer_id, total_amount)`. The canonical key preserves this ordering per the function's documented scope (line 45: "Preserves exact column ordering for B-tree index prefix semantics"). The leading column determines the index prefix, so ordering matters.

---

## Section D — TRAIN/DEV/TEST Memory ID Verification

### D1. Exact TRAIN Memory IDs

From `phase6c_partition_manifest.json` (SHA-256: `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`):

| Memory ID | Case ID | Template | Candidate Key | Partition |
|:---:|:---:|:---:|:---|:---:|
| 1 | CASE-T1-01 | T1 | `orders:btree:(customer_id,)` | **TRAIN** |
| 2 | CASE-T1-02 | T1 | `orders:btree:(customer_id,)` | **TRAIN** |
| 3 | CASE-T1-03 | T1 | `orders:btree:(customer_id,)` | **TRAIN** |
| 4 | CASE-T2-01 | T2 | `orders:btree:(total_amount,)` | **TRAIN** |
| 5 | CASE-T2-02 | T2 | `orders:btree:(total_amount,)` | **TRAIN** |
| 6 | CASE-T2-03 | T2 | `orders:btree:(total_amount,)` | **TRAIN** |
| 7 | CASE-T3-03 | T3 | `orders:btree:(total_amount,customer_id)` | DEV |
| 8 | CASE-T5-01 | T5 | `order_items:btree:(quantity,)` | DEV |
| 9 | CASE-T5-02 | T5 | `order_items:btree:(quantity,)` | DEV |
| 10 | CASE-T7-01 | T7 | `order_items:btree:(quantity,unit_price)` | TEST (Phase 6D) |
| 11 | CASE-T7-02 | T7 | `order_items:btree:(quantity,unit_price)` | TEST (Phase 6D) |
| 12 | CASE-T7-03 | T7 | `order_items:btree:(quantity,unit_price)` | TEST (Phase 6D) |
| 13 | CASE-T8-01 | T8 | `orders:btree:(customer_id,)` | TEST (Phase 6D) |
| 14 | CASE-T8-02 | T8 | `orders:btree:(customer_id,)` | TEST (Phase 6D) |

---

## Section E — Historical Case Support Per Candidate

### E1. TRAIN Support for `customer_id` candidate

**Candidate key:** `orders:btree:(customer_id,)`

TRAIN cases supporting this key: **Memory IDs 1, 2, 3** (template T1: `select * from orders where customer_id = ?`)

| Memory ID | Case ID | Query Text | Verified Measured? |
|:---:|:---:|:---|:---:|
| 1 | CASE-T1-01 | `SELECT * FROM orders WHERE customer_id = 42;` | ✅ |
| 2 | CASE-T1-02 | `SELECT * FROM orders WHERE customer_id = 105;` | ✅ |
| 3 | CASE-T1-03 | `SELECT * FROM orders WHERE customer_id = 278;` | ✅ |

**Policy B support:** 3 TRAIN cases match → `similarity_support` accumulates from 3 token-hash comparisons.  
**Policy C support:** 3 verified measured cases match → `outcome_support` accumulates from 3 (sim × delta) contributions.

### E2. TRAIN Support for `total_amount` candidate

**Candidate key:** `orders:btree:(total_amount,)`

TRAIN cases supporting this key: **Memory IDs 4, 5, 6** (template T2: `select * from orders where total_amount > ?`)

| Memory ID | Case ID | Query Text | Verified Measured? |
|:---:|:---:|:---|:---:|
| 4 | CASE-T2-01 | `SELECT * FROM orders WHERE total_amount > 450.00;` | ✅ |
| 5 | CASE-T2-02 | `SELECT * FROM orders WHERE total_amount > 480.00;` | ✅ |
| 6 | CASE-T2-03 | `SELECT * FROM orders WHERE total_amount > 420.00;` | ✅ |

**Policy B support:** 3 TRAIN cases match → `similarity_support` accumulates.  
**Policy C support:** 3 verified measured cases match → `outcome_support` accumulates.

### E3. TRAIN Support for Composite `(total_amount, customer_id)` candidate

**Candidate key:** `orders:btree:(total_amount,customer_id)`

TRAIN cases with this key: **0** (zero matches)

> [!NOTE]
> Memory ID 7 (CASE-T3-03, DEV) has primary candidate key `orders:btree:(total_amount,customer_id)`.
> However, ID 7 is in the **DEV partition**, not TRAIN. The retrieval corpus for Phase 8 is
> strictly IDs 1–6. ID 7 is **excluded** from policy computation by the TRAIN boundary.

**Policy B support:** 0 matching TRAIN cases → `similarity_support = 0.0` for this candidate.  
**Policy C support:** 0 matching TRAIN cases → `outcome_support = 0.0` for this candidate.

---

## Section F — Template Absence Verification

### F1. T9 (`>= ` template) Absence from All Existing Partitions

Verified computationally via `phase8_hash_verify.py` (read-only, no database access):

| Partition | Templates | T9 hash present? |
|:---:|:---|:---:|
| TRAIN | T1, T2 | ❌ Absent |
| DEV | T3, T5 | ❌ Absent |
| TEST (Phase 6D) | T7, T8 | ❌ Absent |
| Phase 7 (TP-A, TP-D, TP-B) | All new templates | ❌ Absent (verified hash list) |

**T9 hash `8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343` is disjoint from all existing templates.**

### F2. Existing Memory Match

No row in `optimization_memories` (IDs 1–14) has a query text containing `>=`. The closest is T2 which uses `>` and T3 (DEV) which uses `>`. No memory record corresponds to the exact T9 template.

---

## Section G — Policy Eligibility for Historical Support

### G1. Policy B Historical Support

Per `select_similarity()` logic (candidate_selector.py lines 257–360):

1. History cases checked: TRAIN IDs 1–6
2. For each history case, `extract_case_key(h)` is compared to each candidate key
3. If match: `compute_token_hash_similarity(query_text, h.query.text)` is accumulated

**Result:**
- Composite `(total_amount, customer_id)`: **0 TRAIN matches** → `sim_support = 0.0`
- `(total_amount,)`: **3 TRAIN matches** (IDs 4, 5, 6) → `sim_support > 0`
- `(customer_id,)`: **3 TRAIN matches** (IDs 1, 2, 3) → `sim_support > 0`

`total_matching_cases = 6 > 0` → **No fallback**. Policy B has eligible historical support.

### G2. Policy C Historical Support

Per `select_outcome_aware()` logic (candidate_selector.py lines 362–494):

1. Filter to `provenance == measured`, `is_verified == True`, `verification_state == verified_measured`
2. All 6 TRAIN cases pass this filter (verified from Phase 6C partition manifest)

**Result:**
- Composite `(total_amount, customer_id)`: **0 TRAIN matches** → `outcome_support = 0.0`
- `(total_amount,)`: **3 measured matches** (IDs 4, 5, 6) → `outcome_support > 0`
- `(customer_id,)`: **3 measured matches** (IDs 1, 2, 3) → `outcome_support > 0`

`total_measured_matching = 6 > 0` → **No fallback**. Policy C has eligible verified-measured support.

---

## Section H — Extension Compatibility

### H1. Can Phase 6C Partition Be Extended Without Modifying Phase 6D?

**Yes.** The Phase 6C partition lock covers 14 specific cases with 6 specific template hashes. Adding T9 as a Phase 8 extension:

- Does **not** change any existing case's partition assignment
- Does **not** change any locked template hash
- Does **not** add a case to TRAIN, DEV, or the Phase 6D TEST sets
- Creates a **new standalone Phase 8 TEST partition** separate from the Phase 6D TEST partition

The Phase 6C lock SHA-256 (`b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27`) covers only the original 14 cases. The Phase 8 manifest has its own separate SHA-256.

**Conclusion:** Phase 8 is a forward extension. Phase 6C, 6D, and Phase 7 remain immutable.

---

## Section I — Leakage Verdict

### I1. Template Leakage

| Check | Result |
|:---|:---:|
| T9 hash absent from TRAIN partition | ✅ CLEAN |
| T9 hash absent from DEV partition | ✅ CLEAN |
| T9 hash absent from Phase 6D TEST partition | ✅ CLEAN |
| T9 hash absent from Phase 7 templates | ✅ CLEAN |
| `>` vs `>=` generates distinct canonical forms | ✅ VERIFIED |

### I2. Retrieval Corpus Leakage

| Check | Result |
|:---|:---:|
| Policy B/C see only TRAIN IDs 1–6 | ✅ Required |
| DEV case ID 7 (T3 composite) NOT in retrieval corpus | ✅ Required |
| Phase 6D/7 outcomes NOT available to policies | ✅ Required |
| T9 outcome NOT available to policies before measurement | ✅ Required |

### I3. Parameter Leakage

| Check | Result |
|:---|:---:|
| alpha, beta, lambda_reg locked from Phase 6D | ✅ Values frozen |
| No tuning on T9 outcome | ✅ Required — enforced by sequencing |

### I4. Oracle Sequencing

| Check | Result |
|:---|:---:|
| Policy selection precedes physical measurement | ✅ Required by protocol |
| Oracle cannot influence policy selection | ✅ Guaranteed by sequencing |

**OVERALL LEAKAGE VERDICT: CLEAN. No template, retrieval, parameter, or oracle leakage detected.**

---

## Section J — Multi-Candidate Eligibility

### J1. Why This Case Qualifies as a Genuine Multi-Candidate Case

Phase 7's primary structural finding was that Phase 1 generates only **1 eligible candidate** for
two-column predicate queries with a string equality predicate (`status = ?`). Policy divergence
was impossible.

This Phase 8 case differs structurally:

| Factor | Phase 7 Cases | Phase 8 Case |
|:---|:---|:---|
| Predicate types | `total_amount > X AND status = 'Y'` (float range + string equality) | `customer_id = 42 AND total_amount >= 450.00` (int equality + float range) |
| Phase 1 column extraction | `status` not promoted (string literal, low cardinality) | `customer_id` and `total_amount` both numeric-comparable, both promoted |
| HypoPG-eligible candidates | 1 (only `total_amount`) | 3 (composite, `total_amount`, `customer_id`) |
| Policy divergence possible? | No | **Yes** |

The authoritative runtime diagnostic has **already confirmed** three independently HypoPG-validated
candidates. This is not a design prediction — it is an observed fact from the runtime system.

### J2. Candidate Pool Integrity

> [!IMPORTANT]
> The three candidates are taken **exactly as reported by the runtime diagnostic**.
> No candidate generation has been modified, synthesized, or artificially manufactured.
> The experiment uses the Phase 1 output as-is.

---

## Section K — Phase 6C Partition Immutability

The Phase 6C partition is treated as fully immutable:

- No existing case IDs, template assignments, query texts, or partition boundaries are changed
- No cases are added to the Phase 6C corpus (IDs 1–14)
- No memory rows are modified
- The Phase 8 extension creates its own independent partition record
- The Phase 6C manifest SHA-256 must be re-verified before Phase 8 physical execution begins

---

## Section L — Phase 6D and Phase 7 Immutability

| Artifact | Modified? |
|:---|:---:|
| `research/PHASE6C_PARTITION_LOCK.md` | ❌ Not modified |
| `research/phase6c_partition_manifest.json` | ❌ Not modified |
| `research/phase6d_experiment_manifest.json` | ❌ Not modified |
| `research/phase7_experiment_manifest.json` | ❌ Not modified |
| `research/phase7_selection_results.json` | ❌ Not modified |
| `research/PHASE7_EXECUTION_REPORT.md` | ❌ Not modified |
| `research/PHASE7_AUDIT.md` | ❌ Not modified |
| `optimization_memories` (IDs 1–14) | ❌ Not modified |
| Any production `autodba-main` file | ❌ Not modified |

---

## Section M — Candidate Generation Integrity

The three candidates were **not synthesized** by this audit. They were provided as
the authoritative runtime diagnostic output. This audit verifies that:

1. The three candidate keys are correctly canonicalized
2. Their TRAIN support is correctly attributed
3. No fourth candidate has been added or removed
4. The `is_baseline` assignment (composite = True, singles = False) is consistent with
   Phase 1 behaviour: the composite captures all predicate columns and is the planner's
   primary recommendation

---

## Audit Verdict

> [!IMPORTANT]
> **PHASE 8 CASE IS ELIGIBLE FOR PHYSICAL EXECUTION**
>
> All leakage, partition, template, and sequencing controls are satisfied.
> The following conditions must be met before physical measurement begins:
>
> 1. `phase8_experiment_manifest.json` must be finalized and SHA-256 recorded
> 2. Policy selections (A, B, C) must be computed and written to `phase8_selection_results.json`
> 3. The Phase 6C manifest SHA-256 must be re-verified at script start
> 4. `optimization_memories` count must be confirmed = 14 at script start

---

## Methodological Limitation (Mandatory)

> [!WARNING]
> This is **one informative multi-candidate unseen-template case**. One case is not sufficient
> for a strong comparative conclusion about Policy B or C superiority over Policy A.
>
> The experiment can establish whether policy divergence **occurs** and its **direction**,
> but cannot establish statistical significance or generalizability.
>
> Adequate comparative evidence would require ≥ 5–10 independent multi-candidate TEST cases
> across diverse templates and tables.

---

*Audit completed: 2026-10-03. No production code was modified. No database writes were performed.*
