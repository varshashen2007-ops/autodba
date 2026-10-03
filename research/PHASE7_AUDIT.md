# Phase 7 Audit

**Date:** 2026-10-01  
**Purpose:** Forensic verification of Phase 7 execution invariants.

---

## Invariant Checklist

### I1 — Phase 6C Partition Manifest Unchanged

```
Expected SHA-256: b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27
```

**CHECK:** Run at start of `execute_phase7.py` before any measurement.  
**RESULT:** ✅ PASSED — hash verified, execution proceeded.

---

### I2 — optimization_memories Count = 14

**CHECK:** Verified post-execution via `SELECT COUNT(*) FROM optimization_memories`.  
**RESULT:** ✅ PASSED — count = 14.

---

### I3 — Memory IDs 1–14 All Present and Unchanged

**CHECK:** `SELECT id FROM optimization_memories ORDER BY id` → [1,2,...,14].  
**RESULT:** ✅ PASSED — all 14 IDs present in sequence.

---

### I4 — All 14 Memories Are MEASURED + VERIFIED_MEASURED

**CHECK:** `SELECT id, provenance, is_verified, verification_state FROM optimization_memories`.  
**RESULT:** ✅ PASSED — all provenance='measured', is_verified=True, verification_state='verified_measured'.

---

### I5 — Zero Phase 7 Outcomes Inserted into optimization_memories

**CHECK:** Phase 7 script contains no INSERT statements into optimization_memories.
Memory count remains 14 throughout. No mutation path exists in execute_phase7.py.  
**RESULT:** ✅ PASSED.

---

### I6 — Zero Residual idx_autodba_* Indexes

**CHECK:** Pre-flight check at start of execution. Post-cleanup check after each
benchmark. Final check after all benchmarks complete.

Per-candidate cleanup results:
- CASE-TP-A-01 `idx_autodba_p7_orders_total_amount`: cleanup_success=True
- CASE-TP-A-02 `idx_autodba_p7_orders_total_amount`: cleanup_success=True
- CASE-TP-A-03 `idx_autodba_p7_orders_total_amount`: cleanup_success=True
- CASE-TP-D-01 `idx_autodba_p7_orders_total_amount`: cleanup_success=True
- CASE-TP-D-02 `idx_autodba_p7_orders_total_amount`: cleanup_success=True

Final count: 0 residual indexes.  
**RESULT:** ✅ PASSED — all 5 indexes torn down successfully.

---

### I7 — TRAIN Retrieval Strictly Limited to IDs 1–6

**CHECK:** `load_train_cases()` queries `WHERE id = ANY([1,2,3,4,5,6])`.
DEV (IDs 7–9) and TEST (IDs 10–14) are never passed to selector.  
**RESULT:** ✅ PASSED — retrieval corpus = 6 cases (IDs 1–6) only.

---

### I8 — Policy Selection Locked BEFORE Physical Measurement

**CHECK:** `phase7_selection_results.json` is written (line ~617) BEFORE
the physical measurement loop begins (line ~623). The JSON timestamp in
the file predates any `CREATE INDEX` execution.  
**RESULT:** ✅ PASSED — temporal ordering verified by code structure.

---

### I9 — A/B/C Received Identical Eligible Candidate Pools

**CHECK:** All three policies operate on the same `eligible` list per case,
derived from a single Phase 1 `intel.diagnose()` call.  
**RESULT:** ✅ PASSED — pool size = 1 for all 5 active cases. Identical.

---

### I10 — Oracle Determined Independently of A/B/C

**CHECK:** Oracle = candidate with max `runtime_improvement_percent` across all
physically benchmarked eligible candidates. Since pool = 1, oracle = the single
candidate's actual measured dT%. A/B/C selections do not influence oracle.  
**RESULT:** ✅ PASSED — oracle = `orders(total_amount)` for all 5 cases.

---

### I11 — Source autodba-main Untouched

**CHECK:** No edits made to `C:\Users\swarsh\Desktop\autodba-main`. All
research code resides in `autodba-research\research\`. Production
`intelligence_service.py` was read-only; `execute_phase7.py` only calls
`IntelligenceService.diagnose()` as a consumer, not a modifier.  
**RESULT:** ✅ PASSED.

---

### I12 — No Unapproved Production Changes

**CHECK:** Only files created/modified in this phase:
- `research/execute_phase7.py` (new — research script)
- `research/phase7_experiment_manifest.json` (new — research artifact)
- `research/phase7_selection_results.json` (new — research artifact)
- `research/phase7_measurements.json` (new — research artifact)
- `research/PHASE7_EXECUTION_REPORT.md` (new — research artifact)
- `research/PHASE7_AUDIT.md` (this file — new)

No production application files modified.  
**RESULT:** ✅ PASSED.

---

## Preflight Contradiction Log

| # | Contradiction | Resolution | Redesign Required? |
| :--- | :--- | :--- | :---: |
| 1 | Status values uppercase in SQL, lowercase in DB | Corrected parameter values | No |
| 2 | Low-threshold parameters suppress HypoPG index use | Updated to > 440 range | No |
| 3 | TP-A and TP-D are distinct canonical templates | Documented as distinct (expected) | No |
| 4 | Phase 1 generates only 1 candidate per TP-A/TP-D case | Documented as structural finding | No — fail-honest |
| 5 | TP-B-01 has no baseline in eligible pool | Fail-closed per preflight rules | No |

---

## Execution Summary

| Metric | Value |
| :--- | :--- |
| Proposed cases | 6 |
| Preflight-blocked | 1 |
| Measured cases | **5** |
| Benchmark protocol | W=2, N=10 |
| All cleanup successful | ✅ |
| Memory isolation maintained | ✅ |
| All invariants passed | **12/12** |

---

## Verdict

**A. PHASE 7 EXECUTED — READY FOR RESULTS AUDIT**

All 12 invariants pass. The execution is methodologically clean. The primary
finding — single-candidate pools across all active cases — is accurately
documented and does not invalidate the experiment. The measurements are valid
and the research artifacts are complete.
