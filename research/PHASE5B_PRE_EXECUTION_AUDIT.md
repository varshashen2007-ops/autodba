# Phase 5B: Pre-Execution Safety Audit

**Repository**: `C:\Users\swarsh\Desktop\autodba-research`  
**Branch**: `research/outcome-aware-ranking`  
**Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` (Pristine and untouched)  
**Audit Scope**: Rigorous pre-execution audit of `research/measured_case_runner.py`, `research/PHASE5B_EXECUTION_DESIGN.md`, and underlying backend service implementations prior to any Docker startup or database connectivity.

---

## 1. Closed-Loop Interface Verification

### Signature of `ClosedLoopService.execute()`
```python
def execute(
    self,
    *,
    approval_id: str,
    query_text: str,
    incident_type: str,
    diagnosis: Dict[str, Any],
    recommendation: Optional[OptimizationRecommendation] = None,
) -> Dict[str, Any]
```

### Responsibility Audit Across Stages
1. **Approval**: Performed by `ApprovalService.approve(approval_id, approved_by)` prior to invoking `ClosedLoopService`. `ClosedLoopService` verifies approval existence via `default_approval_service.get_approval_request(approval_id)`.
2. **HypoPG Validation**: Performed by `HypoPGValidatorService.validate_candidate()` during diagnosis (`IntelligenceService`). `RemediationService` re-validates `approval.recommendation.hypopg_validated is True` before opening a DDL transaction.
3. **Physical Remediation**: Performed exclusively by `RemediationService.apply_approved_recommendation()`.
4. **BEFORE Benchmarking**: Performed by `BenchmarkService.benchmark()` via `measure_query(disable_indexes=True)` using session-level `SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off;`.
5. **AFTER Benchmarking**: Performed by `BenchmarkService.benchmark()` via `measure_query(disable_indexes=False)`.
6. **Physical Verification**: Performed by `RemediationService._verify_created_index()` which queries `pg_indexes` to confirm physical index name and column order.
7. **Memory Persistence**: Performed by `MemoryService.create_memory()` called inside `ClosedLoopService.execute()`.

### Runner Compatibility Check
In `MeasuredCaseRunner.execute_pilot_case()`, the call is:
```python
loop_result = closed_loop.execute(
    approval_id=approved.approval_id,
    query_text=query,
    incident_type=diag_resp.diagnosis.incident_type or "missing_index",
    diagnosis=diag_resp.diagnosis.analysis,
    recommendation=approved.recommendation,
)
```
- **Finding**: The runner passes semantically correct, strongly-typed arguments conforming exactly to `ClosedLoopService.execute()`.

---

## 2. Index Ownership & Cleanup Audit

### Index Name Generation in `RemediationService`
`RemediationService.generate_index_name` generates `idx_autodba_{table}_{cols_joined}` (e.g. `idx_autodba_orders_customer_id`), truncated with an MD5 hash to 63 bytes if necessary.

### Safety Invariant Checklist
| Question | Audit Finding | Safety Assessment |
|---|---|---|
| **A. Could a pre-existing index have the same name/definition?** | **YES**. If an identical index already existed on the table, `RemediationService` detects it via `_find_equivalent_index()`, returns `status = ALREADY_APPLIED`, and sets `index_name = existing_index_name`. | ⚠️ **UNSAFE DEFECT IN RUNNER** |
| **B. Could a previous failed run leave an index with that name?** | **YES**. If a prior test crashed before cleanup, `idx_autodba_orders_customer_id` could remain in `pg_indexes`. `RemediationService` would return `ALREADY_APPLIED`. | ⚠️ **UNSAFE DEFECT IN RUNNER** |
| **C. Could another candidate create an additional physical index?** | **NO**. The closed loop processes exactly one approved `OptimizationRecommendation` per execution. | ✅ Safe |
| **D. Does the runner track every physical object created?** | **YES**. It tracks `remediation.index_name`. | ✅ Safe |
| **E. Could cleanup accidentally remove a pre-existing index?** | **YES!** If `remediation.status == ALREADY_APPLIED`, the index was **not created by this run**. Because `MeasuredCaseRunner` currently drops `created_index_name` unconditionally in `finally:`, **it would drop the pre-existing index!** | 🚨 **CRITICAL FLAW** |

### Specific Failure Mode
If the database already had `idx_autodba_orders_customer_id` before the pilot was executed:
1. `RemediationService` returns `status = ALREADY_APPLIED` and `index_name = "idx_autodba_orders_customer_id"`.
2. `MeasuredCaseRunner` enters `finally:` and calls `cleanup_index("idx_autodba_orders_customer_id", "orders")`.
3. `cleanup_index` executes `DROP INDEX idx_autodba_orders_customer_id;`.
4. The database is mutated destructively by deleting an index that was present before the run.

---

## 3. Reset Validity Audit (Strategy A)

### Scope of Control for Strategy A (`DROP INDEX` + `DISCARD ALL` + `pg_indexes` audit)

| State Dimension | Controlled by Strategy A? | Mechanism & Limitations |
|---|---|---|
| **Index-State Reset** | **YES** | `DROP INDEX` physically removes the index relation from PostgreSQL disk and catalogs. Verified via `pg_indexes`. |
| **Session-State Reset** | **YES** | `DISCARD ALL` resets session temporary tables, prepared query plans, sequence caches, and session variables. |
| **Planner & Statistics State** | **NO** | `pg_statistic` / `pg_stat_user_tables` are not reset. If `ANALYZE` was triggered, distribution stats remain. |
| **Buffer Cache State** | **NO** | Table heap pages read during benchmarking remain resident in PostgreSQL `shared_buffers` and OS page cache. |
| **Table Data State** | **N/A (Untouched)** | Pilot query is strictly read-only; no table rows are inserted, updated, or deleted. |
| **Schema Object State** | **YES** | No other tables, views, or functions are created. |

### Evaluation: Is Strategy A Sufficient for a Single Pilot Case?
- **Verdict**: **YES, for a single pilot case only**, provided the pre-existing index drop bug (Section 2) is fixed.
- **Narrow Justification**:
  - The pilot query is strictly read-only.
  - No DML or table statistics mutations occur.
  - The physical index relation is the only persistent database mutation made during the pilot.
  - `DISCARD ALL` invalidates cached plans.
  - Discarded warmup runs ($W=2$) within `BenchmarkService` mitigate cold-vs-warm cache variance for that query.
- **Limitation for Future Multi-Case Evaluation**:
  - Strategy A is **not** sufficient for batch evaluation across dozens of sequential cases due to cumulative buffer cache thermal bias and statistics drift. Multi-case evaluations will require full database reseed.

---

## 4. Before / After Benchmark Validity

`BenchmarkService.benchmark()` executes controlled measurements:

| Factor | BEFORE Measurement | AFTER Measurement | Equivalent? |
|---|---|---|---|
| **SQL Query Text** | `safe_query` | `safe_query` | ✅ Exact match |
| **Parameters & Options** | `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` | `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` | ✅ Exact match |
| **Run Count** | `runs` (default 10) | `runs` (default 10) | ✅ Exact match |
| **Warmup Count** | `warmup_runs` (default 2, discarded) | `warmup_runs` (default 2, discarded) | ✅ Exact match |
| **Transaction Boundary** | Isolated transaction block | Isolated transaction block | ✅ Exact match |
| **Planner Scan Configuration** | `SET LOCAL enable_indexscan=off;`<br>`SET LOCAL enable_bitmapscan=off;` | `SET LOCAL enable_indexscan=on;`<br>`SET LOCAL enable_bitmapscan=on;` | ✅ Controlled difference |
| **Cache Order Bias** | Executed 1st (heats buffer cache) | Executed 2nd (reads from warm buffer cache) | ⚠️ Uncontrolled thermal bias |

### Methodological Finding
- Because BEFORE executes first, it pulls heap blocks into PostgreSQL `shared_buffers`.
- AFTER executes second, benefiting from pre-warmed buffer cache.
- While `warmup_runs=2` warms the index pages for AFTER, the overall execution time for AFTER may show slight thermal advantage compared to a completely cold execution.
- This is acceptable for relative ranking comparison if consistently applied across all candidate evaluations.

---

## 5. Table Data Mutation Audit

- `DatabaseMonitorService.explain_query`: Read-only `EXPLAIN (FORMAT JSON)`.
- `HypoPGValidatorService.validate_candidate`: In-memory simulation via `hypopg_create_index()` + `hypopg_reset()`.
- `RemediationService.apply_approved_recommendation`: Executes `CREATE INDEX` DDL only.
- `BenchmarkService.benchmark`: Enforces `validate_read_only_query()` and executes `EXPLAIN ANALYZE` on read-only queries only.
- `MemoryService.create_memory`: Inserts into `optimization_memories` system table.
- **Finding**: **Zero user data mutation**. Tables `orders`, `customers`, `products`, and `order_items` are never mutated.

---

## 6. Database Target Safety Guard Audit

### Runner Safety Implementation Analysis
1. **Host Validation**: Checks `settings.POSTGRES_HOST in {"localhost", "127.0.0.1", "postgres", "test-db"}` or starts with `localhost`.
2. **Database Name Validation**: Rejects `POSTGRES_DB` if `"prod"` or `"production"` is in the string.
3. **Credentials & Config**: Loaded securely via Pydantic `SettingsConfigDict(env_file=".env")`; no hardcoded credentials in runner.

### Critical Limitations & Non-Guarantees
- **Localhost Ambiguity**: `localhost:5432` does **not** guarantee a research database. A developer might run a production or staging database locally.
- **Port Check Missing**: The runner does not inspect `POSTGRES_PORT` (e.g. 5432 vs 5433).
- **Required Pre-Flight Protection**: The runner must verify the presence of the AutoDBA seed tables (`customers`, `products`, `orders`) and research extensions before executing any DDL.

---

## 7. Memory Integrity Audit

### Trace of Memory Creation
```
ClosedLoopService.execute()
  ├── is_verified = (benchmark.status == "completed" and remediation.status in ("applied", "already_applied") and remediation.verification_passed)
  ├── provenance = MEASURED if is_verified else UNVERIFIED
  ├── verification_state = VERIFIED_MEASURED if is_verified else UNVERIFIED
  └── MemoryService.create_memory(...)
        └── Strict Enforcer:
              if provenance == MEASURED and is_verified:
                  is_verified = True, verification_state = VERIFIED_MEASURED
              else:
                  provenance = UNVERIFIED, is_verified = False, verification_state = UNVERIFIED
```
- **Finding**: **Memory integrity is strictly protected**. The runner cannot directly manufacture or forge `MEASURED` / `is_verified=True` / `VERIFIED_MEASURED` records.

---

## 8. Failure Modes & Edge Case Matrix

| Scenario | Behavior in Pipeline | Database Left in Safe State? | False Measured Case Created? |
|---|---|---|---|
| **1. HypoPG fails** | `SafetyAssessor` blocks approval $\rightarrow$ `ApprovalService` rejects $\rightarrow$ Loop stops. | ✅ Yes (untouched) | ❌ No |
| **2. Approval fails** | `ClosedLoopApprovalError` raised $\rightarrow$ Loop stops. | ✅ Yes (untouched) | ❌ No |
| **3. DDL execution fails** | `engine.begin()` rolls back transaction $\rightarrow$ `RemediationExecutionError` raised. | ✅ Yes (rolled back) | ❌ No |
| **4. AFTER benchmark fails** | `BenchmarkExecutionError` raised $\rightarrow$ Index dropped in `finally:`. | ✅ Yes (index dropped) | ❌ No |
| **5. Index verification fails** | `RemediationVerificationError` raised $\rightarrow$ Index dropped in `finally:`. | ✅ Yes (index dropped) | ❌ No |
| **6. Memory persistence fails** | SQLAlchemy exception raised $\rightarrow$ Index dropped in `finally:`. | ✅ Yes (index dropped) | ❌ No |
| **7. Python exception mid-run** | Caught by `finally:` $\rightarrow$ `cleanup_index` drops created index. | ✅ Yes (index dropped) | ❌ No |
| **8. Cleanup itself fails** | `cleanup_success = False` recorded in result. | ⚠️ Uncleaned index remains | ❌ No false case |

---

## 9. Baseline Repository & Git Verification

- **Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` has 110 files and is 100% untouched.
- **Production Source**: Zero files modified under `autodba-main/backend`.
- **Git Remotes**: Zero remotes configured.
- **Git Status**: Phase 5 artifacts remain strictly untracked/uncommitted.

---

## 10. FINAL VERDICT

# **B. SAFE ONLY AFTER SPECIFIC FIX**

### Minimum Required Fixes Before Execution:
1. **Fix Index Cleanup Ownership Check (`measured_case_runner.py`)**:
   - In `execute_pilot_case`, the runner must only drop `created_index_name` if `remediation.status == RemediationStatus.APPLIED` (meaning newly created by this run).
   - If `remediation.status == RemediationStatus.ALREADY_APPLIED`, the index was pre-existing and **must not be dropped**.
2. **Add Pre-Flight Equivalent Index Check**:
   - Before executing the pilot case, check `fetch_table_indexes(target_table)`. If an equivalent index on `(table, columns)` already exists, raise an error or warn the user to clean the test database first to guarantee a clean baseline.
3. **Add Table Existence Pre-Flight**:
   - Check that `orders`, `customers`, `products`, `order_items` exist before running diagnosis.

---

### Audit Conclusion
The design and closed-loop integration are structurally sound, but the **unconditional index cleanup flaw** prevents an unconditional "SAFE TO EXECUTE AS-IS" verdict. Applying the specific ownership check fix in `measured_case_runner.py` will render the runner fully safe for pilot execution.
