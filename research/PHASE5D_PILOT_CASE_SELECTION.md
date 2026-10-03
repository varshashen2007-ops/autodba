# Phase 5D: First Pilot Case Selection Audit

**Repository**: `C:\Users\swarsh\Desktop\autodba-research`  
**Branch**: `research/outcome-aware-ranking`  
**Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` (Pristine and untouched)  
**Database Target**: `autodba-main-postgres-1` (PostgreSQL 17.11, database `autodba`)  
**Scope**: Rigorous read-only selection and verification of the primary pilot case to exercise the AutoDBA missing-index closed loop.

---

## 1. Executive Summary & Selection Verdict

# **A. PILOT CASE SELECTED — READY FOR REVIEW**

A concrete, deterministic pilot case has been identified, traced through the complete AutoDBA pipeline, and verified against the live research database:

- **Pilot SQL Query**: `SELECT * FROM orders WHERE customer_id = 42;`
- **Target Relation**: `orders`
- **Candidate Index**: `orders (customer_id)` USING `btree`
- **Current Baseline**: Table `orders` is verified sequentially scanned (cost: `107.50`, 5,000 rows).
- **HypoPG Counterfactual**: Simulates `Bitmap Index Scan` with cost `28.16` (**73.80% planner cost reduction**).
- **Safety Assessment**: Evaluates to `eligible_for_approval: True`, `safety_level: LOW`, `blocking_reasons: []`.
- **Physical Cleanliness**: Zero equivalent indexes exist; zero `idx_autodba_*` indexes exist.

---

## 2. Distinction of Evidence Sources

### Repository-Derived Facts
1. `postgres/init/01-init.sql` deliberately omitted a secondary index on `orders.customer_id` to provide an authentic missing-index baseline.
2. `postgres/init/02-seed.sql` seeded 5,000 orders distributed across 500 customers (`(i - 1) % 500 + 1`). Customer `42` receives exactly 10 deterministic orders.
3. `BottleneckDetector._rule_filtered_seq_scan` triggers `MISSING_INDEX` when a `Seq Scan` node has a filter and its total cost meets `PLAN_SEQ_SCAN_MIN_COST` (50.0).
4. `RecommendationEngine.extract_candidate_columns` uses `_FILTER_OPERAND_RE` to parse `customer_id` from `(customer_id = 42)`.
5. `HypoPGValidatorService` requires $\ge 15.0\%$ planner cost improvement to assign `ValidationVerdict.VALIDATED`.

### Live Database Facts (Verified via Container `autodba-main-postgres-1`)
1. Table `orders` contains exactly **5,000 rows**.
2. Live `EXPLAIN (FORMAT JSON) SELECT * FROM orders WHERE customer_id = 42;` produces:
   - Node Type: `Seq Scan`
   - Startup Cost: `0.00`
   - Total Cost: `107.50`
   - Plan Rows: `10`
   - Filter: `(customer_id = 42)`
3. Live HypoPG simulation (`hypopg_create_index('CREATE INDEX ON orders (customer_id)')`) produces:
   - Node Type: `Bitmap Heap Scan` / `Bitmap Index Scan`
   - Startup Cost: `4.11`
   - Total Cost: `28.16`
   - Plan Rows: `10`
   - Cost Delta: $\frac{107.50 - 28.16}{107.50} \times 100\% = \mathbf{73.80\%}$
4. Live catalog check on `pg_indexes WHERE tablename = 'orders'` confirms only `orders_pkey` and `idx_orders_order_date` exist. `orders(customer_id)` is **100% unindexed**.
5. Live check for `idx_autodba_%` returns **0 rows**.

---

## 3. End-to-End Pipeline Execution Trace for Selected Pilot

```
1. Input Query
   └── SELECT * FROM orders WHERE customer_id = 42;
          │
2. Plan Analyzer & Bottleneck Detection
   ├── Raw Plan: Seq Scan on orders (cost 107.50, filter customer_id = 42)
   └── Findings: MISSING_INDEX & FILTERED_SEQ_SCAN on orders
          │
3. Candidate Generation
   ├── Extracted Columns: ['customer_id']
   └── Candidate: orders(customer_id) [is_baseline=True]
          │
4. HypoPG Counterfactual Simulation
   ├── Original Cost: 107.50 -> Simulated Cost: 28.16
   ├── Improvement: 73.80% (>= 15.0% threshold)
   └── Verdict: VALIDATED
          │
5. Safety Assessment (SafetyAssessor)
   ├── Status: VALIDATED (Passed)
   ├── HypoPG Validation: Confirmed (Passed)
   ├── Cost Improvement: 73.80% >= 15% (Passed)
   ├── Confidence: HIGH (Passed)
   ├── Risk: LOW (Single-column B-tree) (Passed)
   ├── SQL Preview: CREATE INDEX idx_autodba_orders_customer_id ON orders (customer_id); (Passed)
   └── Result: eligible_for_approval = True
          │
6. Human Approval Gate (ApprovalService)
   ├── create_approval_request() -> PENDING (approval_id generated)
   └── approve(approved_by="research_runner") -> APPROVED
          │
7. Physical Remediation (RemediationService via ClosedLoopService)
   ├── Snapshot & Safety Re-check: Passed
   ├── Pre-Flight Equivalent Index Check: None existing
   ├── DDL Execution: CREATE INDEX idx_autodba_orders_customer_id ON orders (customer_id);
   └── Post-DDL Verification: Confirmed in pg_indexes (verification_passed = True)
          │
8. Runtime Benchmarking (BenchmarkService via ClosedLoopService)
   ├── BEFORE: enable_indexscan=off -> Seq Scan (mean execution time T_before)
   ├── AFTER: enable_indexscan=on -> Bitmap Index Scan (mean execution time T_after)
   └── Runtime Improvement: Delta = (T_before - T_after) / T_before * 100.0%
          │
9. Memory Persistence (MemoryService via ClosedLoopService)
   ├── Provenance: CaseProvenance.MEASURED
   ├── is_verified: True
   ├── Verification State: OutcomeVerificationState.VERIFIED_MEASURED
   └── OptimizationMemoryModel row inserted into PostgreSQL
          │
10. State Reset & Teardown (MeasuredCaseRunner)
   ├── DROP INDEX IF EXISTS idx_autodba_orders_customer_id;
   ├── DISCARD ALL;
   └── pg_indexes verification confirms relation returned to baseline
```

---

## 4. Complete Pilot Case Specification

| Field | Specification |
|---|---|
| **A. Exact SQL Query** | `SELECT * FROM orders WHERE customer_id = 42;` |
| **B. Parameters** | Parameter literal `42` (customer ID) |
| **C. Incident Type** | `missing_index` |
| **D. Diagnosis Required** | `BottleneckFinding(finding_type=MISSING_INDEX, relation='orders', evidence={'filter': '(customer_id = 42)', 'total_cost': 107.50})` |
| **E. Target Table** | `orders` |
| **F. Ordered Candidate Columns** | `['customer_id']` |
| **G. Index Method** | `btree` |
| **H. Why Candidate is Absent** | Deliberately omitted in `01-init.sql`; verified absent in live `pg_indexes`. |
| **I. Why Pipeline Can Process It** | Meets all cost thresholds ($107.50 \ge 50.0$), extracts safely without hallucination, passes HypoPG ($73.80\% \ge 15.0\%$), passes 7 safety checks, matches DDL templates. |
| **J. BEFORE / AFTER Query** | `SELECT * FROM orders WHERE customer_id = 42;` |
| **K. Known Limitations** | 5,000-row table produces low-millisecond latencies; warmup runs ($W=2$) and repeated runs ($N=10$) are essential to stabilize timing statistics. |

---

## 5. Explicit Statements of Non-Execution

1. **Zero physical indexes were created or dropped**.
2. **Zero measured cases were executed**.
3. **`MeasuredCaseRunner.execute_pilot_case()` was NOT called**.
4. **`ClosedLoopService.execute()` was NOT called**.
5. **Zero table data mutations occurred**.
6. **Zero production application files or research logic files were modified**.
7. **`C:\Users\swarsh\Desktop\autodba-main` remains 100% pristine and untouched**.
