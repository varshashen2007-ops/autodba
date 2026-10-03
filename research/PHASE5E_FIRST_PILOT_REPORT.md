# Phase 5E: First Controlled Live Pilot Execution Report

**Date:** 2026-10-01  
**Target Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**Original Source Copy:** `C:\Users\swarsh\Desktop\autodba-main` (Pristine, 110 files untouched)  
**Execution Harness:** `research/measured_case_runner.py`  
**Database Host:** Isolated Docker container `autodba-main-postgres-1` (PostgreSQL 17.11, HypoPG 1.4.3, pg_stat_statements 1.11)  
**Final Verdict:** `A. PILOT SUCCESSFUL — VERIFIED MEASURED CASE CREATED`

---

## 1. Pilot Configuration

| Attribute | Specification |
| :--- | :--- |
| **Case ID** | `measured_orders_customer_id` |
| **Evaluated Query** | `SELECT * FROM orders WHERE customer_id = 42;` |
| **Incident Type** | `missing_index` |
| **Target Relation** | `public.orders` (5,000 rows) |
| **Candidate Index Method** | `btree` |
| **Candidate Target Columns** | `['customer_id']` |
| **Index Identifier** | `idx_autodba_orders_customer_id` |
| **Approval Role** | `research_runner` |
| **Warmup Iterations ($W$)** | 2 |
| **Benchmark Iterations ($N$)** | 10 |
| **Auto Cleanup** | `True` (Ownership-aware index teardown) |

---

## 2. Baseline State (Pre-Flight Verification)

Before triggering execution, the runner executed physical and schema pre-flight verifications:
1. **Host Whitelist Check:** Confirmed host `localhost` is within `ALLOWED_RESEARCH_HOSTS`.
2. **Schema & Extension Presence:** Verified `customers`, `products`, `orders`, `order_items`, and extensions `hypopg`, `pg_stat_statements`.
3. **Physical Relation Index Baseline:**
   - `orders_pkey`: `CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)`
   - `idx_orders_order_date`: `CREATE INDEX idx_orders_order_date ON public.orders USING btree (order_date)`
   - Equivalent index on `orders(customer_id)`: **ABSENT**
4. **AutoDBA Transient Indexes:** Count of `idx_autodba_*` indexes = **0**
5. **Historical Memory Table:** Count of rows in `optimization_memories` = **0**

---

## 3. Actual Execution Trace

The authoritative AutoDBA pipeline executed sequentially without skipping any validation gate:

1. **Step 1: Deterministic Diagnosis & HypoPG Simulation (`IntelligenceService.diagnose`)**
   - AST Parser parsed the query and extracted predicate `customer_id = 42` on table `orders`.
   - `PlanAnalyzer` detected `Seq Scan` with filter condition `(customer_id = 42)` (estimated cost: `107.50`).
   - `BottleneckDetector` raised `BottleneckFinding` of type `missing_index` with `Severity.HIGH`, `Confidence.HIGH`.
   - `RecommendationEngine` generated deterministic candidate `orders(customer_id)`.
   - `HypoPGValidator` created simulated index `<13630>btree_orders_customer_id`, evaluated planner cost drop to `28.16` (`73.80%` improvement, plan transitioned to `Bitmap Heap Scan`), and tore down the hypothetical index.
2. **Step 2: Pre-Flight Equivalent Index Check**
   - Inspected relation `orders` to confirm no pre-existing physical index covered `customer_id`.
3. **Step 3: Formal Human Approval Gate (`ApprovalService`)**
   - Evaluated `SafetyAssessor`: `eligible_for_approval = True`, `safety_level = SafetyLevel.LOW`.
   - Generated `ApprovalRequest` ID `appr_d8a163f60cea`.
   - Explicitly transitioned approval status to `ApprovalStatus.APPROVED` by actor `research_runner`.
4. **Step 4: Authoritative Closed-Loop Execution (`ClosedLoopService.execute`)**
   - **Physical Remediation (`RemediationService`):** Executed `CREATE INDEX CONCURRENTLY idx_autodba_orders_customer_id ON orders USING btree (customer_id);` (Remediation ID: `rem_a430d842de75`, status: `applied`, `verification_passed = True`).
   - **Empirical Benchmarking (`BenchmarkService`):** Benchmark ID `bench_396081828ec2` conducted 2 warmups and 10 measured repetitions for both pre-remediation (simulated index disable) and post-remediation execution.
   - **Memory Persistence (`MemoryService`):** Stored verified measured memory record with ID `1` in `optimization_memories`.
5. **Step 5: Invariant Verification**
   - Confirmed memory `provenance == CaseProvenance.MEASURED` and `is_verified == True`.
6. **Step 6: Ownership-Aware Index Teardown (`cleanup_index`)**
   - `RemediationStatus.APPLIED` confirmed that this specific run created `idx_autodba_orders_customer_id`.
   - Executed `DROP INDEX IF EXISTS idx_autodba_orders_customer_id;` and `DISCARD ALL;`.
   - Verified physical removal from PostgreSQL catalog.

---

## 4. BEFORE Measurement (Baseline / Unindexed)

- **Access Strategy:** `Seq Scan on orders`
- **Filter Condition:** `(customer_id = 42)`
- **Planner Estimated Cost:** `107.50`
- **Rows Filtered Out:** 4,990 rows
- **Rows Returned:** 10 rows
- **Shared Hit Blocks:** 45 buffer blocks
- **Warmup Runs Discarded:** 2 runs
- **Measured Repetitions ($N=10$):**
  `[0.298 ms, 0.188 ms, 0.175 ms, 0.394 ms, 0.299 ms, 0.375 ms, 0.257 ms, 0.300 ms, 0.268 ms, 0.304 ms]`
- **Mean Execution Time ($T_{\text{before}}$):** **`0.2858 ms`**
- **Median Execution Time:** `0.2985 ms`
- **Min / Max Execution Time:** `0.1750 ms` / `0.3940 ms`
- **Standard Deviation:** `0.0695 ms`
- **Coefficient of Variation ($\text{CoV}$):** `0.2433`

---

## 5. AFTER Measurement (Physical Index Active)

- **Access Strategy:** `Bitmap Heap Scan on orders` using `Bitmap Index Scan on idx_autodba_orders_customer_id`
- **Index Condition:** `(customer_id = 42)`
- **Planner Estimated Cost:** `28.41` (Index Scan cost `4.36` + Heap Scan cost `24.05`)
- **Rows Filtered Out:** 0 rows (Exact index match)
- **Rows Returned:** 10 rows
- **Shared Hit Blocks:** 14 buffer blocks (12 heap blocks + 2 index blocks)
- **Warmup Runs Discarded:** 2 runs
- **Measured Repetitions ($N=10$):**
  `[0.031 ms, 0.042 ms, 0.035 ms, 0.033 ms, 0.042 ms, 0.031 ms, 0.023 ms, 0.025 ms, 0.024 ms, 0.043 ms]`
- **Mean Execution Time ($T_{\text{after}}$):** **`0.0329 ms`**
- **Median Execution Time:** `0.0320 ms`
- **Min / Max Execution Time:** `0.0230 ms` / `0.0430 ms`
- **Standard Deviation:** `0.0076 ms`
- **Coefficient of Variation ($\text{CoV}$):** `0.2308`

---

## 6. Measured Performance Delta

$$\Delta T = T_{\text{before}} - T_{\text{after}} = 0.2858\text{ ms} - 0.0329\text{ ms} = 0.2529\text{ ms}$$

$$\text{Runtime Improvement} = \frac{0.2858 - 0.0329}{0.2858} \times 100\% = \mathbf{88.49\%}$$

$$\text{Speedup Factor} = \frac{0.2858}{0.0329} = \mathbf{8.69\times}$$

$$\text{Planner Cost Improvement} = \frac{107.50 - 28.41}{107.50} \times 100\% = \mathbf{73.57\%}$$

### Distinction Between Planner Cost and Measured Runtime Evidence
- **Planner-Cost Evidence:** The PostgreSQL cost estimator predicted a **73.57%** cost reduction (HypoPG estimated 73.80%). Planner cost is a synthetic mathematical heuristic model based on page fetch estimates and CPU tuple operators.
- **Measured Runtime Evidence:** Real end-to-end execution latency across 10 timed executions demonstrated an **88.49%** empirical reduction (latency dropped from 0.2858 ms to 0.0329 ms, buffer block reads dropped from 45 to 14 blocks).

---

## 7. Physical Verification

During physical remediation:
- Remediation executed: `CREATE INDEX CONCURRENTLY idx_autodba_orders_customer_id ON orders USING btree (customer_id);`
- Target table verified: `orders`
- Target columns verified: `['customer_id']`
- Index method: `btree`
- Verification check passed: PostgreSQL catalog confirmed existence of valid, active index `idx_autodba_orders_customer_id`.

---

## 8. Memory Verification

Queried PostgreSQL table `optimization_memories` directly:
- **Total Records:** Exactly **1** record.
- **Record ID:** `1`
- **Incident Type:** `missing_index`
- **Query Text:** `SELECT * FROM orders WHERE customer_id = 42;`
- **Outcome:** `OptimizationOutcome.SUCCESS` (`success`)
- **Outcome Summary:** `"Measured runtime improved by 88.49%. Planner cost change: 73.57%."`
- **Data Provenance:** `CaseProvenance.MEASURED` (`measured`)
- **Is Verified Flag:** `True` (`t`)
- **Verification State:** `OutcomeVerificationState.VERIFIED_MEASURED` (`verified_measured`)
- **Recommendation Snapshot:** Includes full deterministic metadata, SQL preview, risk tier, and trade-offs.
- **Benchmark Snapshot:** Includes full timing distributions, individual run arrays, standard deviations, and buffer block counters.

---

## 9. Cleanup Verification

The runner's `finally` block invoked `cleanup_index("idx_autodba_orders_customer_id", "orders")`:
- Executed `DROP INDEX IF EXISTS idx_autodba_orders_customer_id;`
- Executed `DISCARD ALL;` (resetting cached plan entries)
- Queried `pg_indexes WHERE tablename = 'orders'`: confirmed index `idx_autodba_orders_customer_id` is completely removed.
- Runner reported: `cleanup_success = True`.

---

## 10. Baseline Restoration

Post-execution database state confirmed via direct SQL queries:

```sql
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'orders';
```
**Result:**
- `orders_pkey`: `CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)`
- `idx_orders_order_date`: `CREATE INDEX idx_orders_order_date ON public.orders USING btree (order_date)`
- Transient `idx_autodba_*` indexes count: **0**
- Baseline physical indexes on `orders`: **100% restored to original pre-test state**.

---

## 11. Errors and Warnings

- **Session Transaction Decoupling (Resolved):** In SQLAlchemy 2.0, read queries in `DatabaseMonitorService.explain_query` initiated an implicit transaction on the session. An explicit `db.rollback()` was added in `measured_case_runner.py` prior to `ClosedLoopService` execution, ensuring clean transactional isolation for `MemoryService.create_memory()`.
- **Autocommit for Index Teardown (Resolved):** `DISCARD ALL` requires execution outside a standard transaction block. `cleanup_index` was updated to execute under `isolation_level="AUTOCOMMIT"`.

---

## 12. Methodological Limitations

1. **Single Point Sample:** This pilot represents a single query pattern (`SELECT * FROM orders WHERE customer_id = 42;`) on a 5,000-row synthetic test database. It serves solely to validate that the AutoDBA closed-loop instrumentation, measurement, and memory persistence mechanisms function accurately in an end-to-end setting.
2. **Not General Efficacy Proof:** This single measured result does **NOT** establish general superiority of historical memory retrieval over planner-only baselines across arbitrary workloads.
3. **Policies B and C Not Yet Evaluated:** No ranking policies (Planner-only vs. Unweighted historical vs. Outcome-aware historical) were compared or benchmarked in this phase.
4. **Buffer Pool Warmth:** With $W=2$ warmup runs, all relevant data pages resided in PostgreSQL shared buffers. Real-world cold-cache storage latency may vary.
