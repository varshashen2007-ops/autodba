# Phase 5B: Controlled Measured-Case Execution Design

**Repository**: `C:\Users\swarsh\Desktop\autodba-research`  
**Branch**: `research/outcome-aware-ranking`  
**Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` (Pristine and untouched)  
**Scope**: Architecture and operational design for executing single, controlled, empirical measured cases through the AutoDBA closed-loop engine while guaranteeing strict database state isolation and provenance integrity.

---

## 1. Executive Summary & Design Principles

The objective of Phase 5B is to define and construct the **minimal, non-invasive research runner** required to execute a single legitimate measured optimization case on an isolated PostgreSQL instance.

### Core Architectural Principles
1. **Zero Logic Duplication**: Reuses existing authoritative services (`ClosedLoopService`, `RemediationService`, `BenchmarkService`, `ApprovalService`, `MemoryService`, `IntelligenceService`) without modifying production source code.
2. **Strict Approval & Safety Preservation**: Never bypasses `SafetyAssessor` or `ApprovalService`. Every case must produce a valid `ApprovalRequest` transitioning explicitly from `PENDING` to `APPROVED` with an audit record (`approved_by = "research_runner"`).
3. **Deterministic Physical Isolation & Reset**: Every physical index created during an experiment must be strictly cataloged, verified, and safely dropped post-benchmark, returning the database to its pristine pre-case baseline.
4. **Authentic Provenance**: Generates memory records satisfying `provenance = MEASURED`, `is_verified = True`, and `verification_state = VERIFIED_MEASURED` exclusively through live database execution.

---

## 2. End-to-End Execution Flow for a Single Measured Case

```
                                [ Research Runner ]
                                         │
                    1. Target & Safety Pre-flight Verification
                       (Ensures DB is local/test, not production)
                                         │
                    2. Schema State Capture & Baseline Audit
                       (Captures pre-existing pg_indexes on target table)
                                         │
                    3. Deterministic Diagnosis & Candidate Evaluation
                       (IntelligenceService.diagnose -> CandidateEvaluation)
                                         │
                    4. Safety Assessment & Explicit Approval Gate
                       (ApprovalService.create_approval_request -> approve)
                                         │
                    5. Authoritative Closed-Loop Orchestration
                       (ClosedLoopService.execute)
                       ├── DDL Creation (RemediationService -> CREATE INDEX)
                       ├── DDL Verification (pg_indexes verification)
                       ├── Controlled Benchmarking (BenchmarkService -> EXPLAIN ANALYZE)
                       │   ├── T_before: disabled index scan session
                       │   └── T_after: enabled index scan session
                       └── Provenance-Aware Memory Persistence (MemoryService)
                                         │
                    6. Physical Index Teardown & Baseline Restoration
                       (DROP INDEX <index_name> + DISCARD ALL + pg_indexes audit)
                                         │
                    7. Output Canonical OptimizationCase Record
```

### Detailed Stage Breakdown

### A. How One Legitimate Measured Case is Executed
1. The research runner receives an input query (e.g. `SELECT * FROM orders WHERE customer_id = 42;`) and target table (`orders`).
2. It invokes `IntelligenceService.diagnose()` to analyze the execution plan and generate candidate recommendations.
3. It selects the candidate under evaluation (e.g., the baseline candidate on `orders(customer_id)`).
4. It submits the recommendation to `ApprovalService.create_approval_request()` and explicitly approves it via `ApprovalService.approve(approval_id, approved_by="research_runner")`.
5. It invokes `ClosedLoopService.execute(...)` with the approved request ID.

### B. How the Database is Prepared
1. Pre-flight verification confirms connectivity and extension availability (`pg_stat_statements`, `hypopg`).
2. The runner inspects `pg_indexes` on the target table to ensure no conflicting secondary index exists prior to execution.

### C. How the BEFORE Benchmark is Captured
1. `BenchmarkService.benchmark()` executes $W$ warmups (default 2) followed by $N$ repeated measurements (default 10) of `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) <query>`.
2. Within a dedicated session transaction, it executes `SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off;` to capture the unindexed baseline execution time distribution.
3. Computes `mean_execution_time_ms`, `median_execution_time_ms`, `stddev`, and buffer block statistics.

### D. How the Approved Candidate is Physically Applied
1. `RemediationService.apply_approved_recommendation()` performs snapshot verification on the approved recommendation.
2. Formats a deterministic index name: `idx_autodba_<table_name>_<columns>` (with MD5 hash truncation to 63 bytes if necessary).
3. Executes `CREATE INDEX <index_name> ON <table_name> (<columns>);` within an atomic transaction.

### E. How the AFTER Benchmark is Captured
1. `BenchmarkService.benchmark()` executes $W$ warmups followed by $N$ repeated measurements with `SET LOCAL enable_indexscan = on; SET LOCAL enable_bitmapscan = on;`.
2. Measures physical index utilization, execution time distribution, row counts, and buffer cache hits/reads.
3. Calculates relative speedup:
   $$\Delta = \frac{T_{\text{before}} - T_{\text{after}}}{T_{\text{before}}}$$
   $$\text{runtime\_improvement\_percent} = \Delta \times 100.0$$

### F. How Physical Index Creation is Verified
1. `RemediationService` inspects `pg_indexes WHERE tablename = :table`.
2. Confirms that `indexname` matches the expected generated name and that the indexed column order exactly matches `target_columns`.
3. Sets `RemediationResult.verification_passed = True`.

### G. How the Measured Memory Record is Persisted
1. `ClosedLoopService` confirms `remediation.verification_passed == True` and `benchmark.status == "completed"`.
2. Sets `is_verified = True`, `provenance = CaseProvenance.MEASURED`, and `verification_state = OutcomeVerificationState.VERIFIED_MEASURED`.
3. Invokes `MemoryService.create_memory()` to insert the record into `optimization_memories`.

### H. How the Database is Restored to the Pre-Case State
1. Post-execution, the runner executes `DROP INDEX IF EXISTS <index_name>;`.
2. Re-queries `pg_indexes` to verify that the table has returned to its initial index count.
3. Executes `DISCARD ALL;` to clear session-level query plan caches, prepared statements, and temporary variables.

---

## 3. Database Reset Strategy Analysis

| Strategy | Isolation Level | Execution Speed | Operational Complexity | State Cleanup Completeness | Suitability for Pilot |
|---|---|---|---|---|---|
| **A. Targeted DDL Drop (`DROP INDEX` + `DISCARD ALL`)** | High (for single relation) | Fast (< 100ms) | Low | Completely removes physical index; clears session plans | **Recommended for Single-Case Runner** |
| **B. Database Reseed (`TRUNCATE` / `02-seed.sql`)** | Complete | Moderate (~2-5s) | Medium | Restores initial rows, sequences, and table statistics | Recommended for Multi-Case Batch Runs |
| **C. Disposable Container per Case** | Absolute | Slow (~15-30s per case) | High | Zero state carryover across containers | Overkill for single case; valuable for final benchmark |
| **D. Snapshot / Restore (pg_dump / ZFS)** | Absolute | Moderate (~5-10s) | High | Restores exact binary data blocks | Requires external filesystem tooling |

### Strategy Decision for Phase 5B Pilot
- **Primary Method**: **Strategy A (Targeted DDL Drop + Session Invalidation)**.
  - The runner strictly tracks `remediation.index_name`.
  - In a `finally:` block, the runner executes `DROP INDEX IF EXISTS <index_name>` and verifies `pg_indexes` to confirm removal.
  - Executes `DISCARD ALL` on the database connection.
- **Documented Limitations**:
  1. *Buffer Pool Warmth*: Table heap blocks remain in PostgreSQL `shared_buffers` and OS page cache after execution. Discarded warmup runs partially mitigate this for subsequent queries, but cold-cache benchmarks require container restarts.
  2. *Table Statistics*: Running sequential queries without DML does not alter `pg_statistic`, but if `ANALYZE` is triggered post-index, statistics will reflect index presence until re-analyzed.
  3. *Workload Ordering*: Dependent query sequences may experience altered shared buffer residency.

---

## 4. Research Runner Architecture & Safety Boundaries

The research runner (`research/measured_case_runner.py`) is structured as a non-invasive orchestration harness:

### Safety Guardrails
1. **Target Host Whitelist**:
   - The runner asserts that `settings.POSTGRES_HOST` is strictly `localhost`, `127.0.0.1`, or `postgres` (docker container hostname).
   - If `DATABASE_URL` contains a production hostname or cloud endpoint (e.g. RDS, Cloud SQL), execution is aborted immediately with `RuntimeError`.
2. **Preserved Approval Lifecycle**:
   - The runner creates formal `ApprovalRequest` objects and invokes `ApprovalService.approve(...)`.
   - Bypassing approval or directly setting database state is strictly disallowed.
3. **Idempotent Cleanup in `finally` Block**:
   - Index teardown is placed in a `try...finally` construct to ensure that even if benchmarking or memory persistence throws an unhandled exception, physical schema changes are rolled back.

---

## 5. Interface Verification & Production Compatibility

During the Phase 5A audit, an interface mismatch was discovered in `backend/app/api/v1/remediations.py` (which calls non-existent `RemediationService.remediate`).
- **Research Runner Action**: The research runner does **not** call the broken REST API route.
- It interfaces directly with the Python service layer:
  ```python
  ClosedLoopService(db_session).execute(
      approval_id=approval.approval_id,
      query_text=query,
      incident_type="missing_index",
      diagnosis=diagnosis.analysis,
      recommendation=approval.recommendation,
  )
  ```
- This completely avoids the disconnected REST route while preserving 100% of production business logic, safety checks, and validation rules.

---

## 6. Pilot Execution Plan

1. **Input Case**:
   - Query: `SELECT * FROM orders WHERE customer_id = 42;`
   - Target Table: `orders`
   - Expected Bottleneck: `MISSING_INDEX` / `FILTERED_SEQ_SCAN`
   - Expected Candidate: `orders(customer_id)`
2. **Execution Steps**:
   - Verify connection to local PostgreSQL test database.
   - Run diagnosis and counterfactual validation via `IntelligenceService`.
   - Create and approve `ApprovalRequest`.
   - Run `ClosedLoopService.execute()`.
   - Verify persisted `OptimizationMemoryModel` row.
   - Clean up created index `idx_autodba_orders_customer_id`.
   - Return structured `OptimizationCase` compatible dictionary.
3. **Success Criteria**:
   - `RemediationResult.verification_passed == True`
   - `BenchmarkResult.status == "completed"`
   - `BenchmarkResult.runtime_improvement_percent` is populated with real timing
   - `OptimizationMemory.is_verified == True`
   - `OptimizationMemory.provenance == "measured"`
   - Table `orders` has zero lingering AutoDBA indexes after cleanup.
