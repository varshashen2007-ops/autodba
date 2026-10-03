# Phase 5A: Real Measured-Data Readiness Audit

**Repository**: `C:\Users\swarsh\Desktop\autodba-research`  
**Branch**: `research/outcome-aware-ranking`  
**Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` (Pristine and untouched)  
**Audit Scope**: Static inspection of the end-to-end closed-loop optimization path, benchmarking pipeline, physical remediation engine, human approval boundary, memory persistence invariants, environment requirements, and experimental contamination risks.

---

## 1. Executive Finding

The AutoDBA codebase contains complete, well-structured implementations for each individual stage of the optimization lifecycle:
- Deterministic diagnosis (`PlanAnalyzer`, `BottleneckDetector`)
- Deterministic candidate generation and evaluation (`IntelligenceService._evaluate_candidates`)
- Counterfactual planner simulation (`HypoPGValidatorService`)
- Conservative fail-closed safety assessment (`SafetyAssessor`)
- Auditable human approval tracking (`ApprovalService`)
- Controlled, idempotent physical index creation (`RemediationService`)
- Controlled before-and-after query benchmarking (`BenchmarkService`)
- Provenance-aware optimization memory persistence (`MemoryService`, `ClosedLoopService`)

**Key Architectural Verdict**:
1. **Closed-Loop Feasibility**: The system is **architecturally capable** of generating legitimate measured cases satisfying `provenance = MEASURED`, `is_verified = True`, and `verification_state = VERIFIED_MEASURED` via `ClosedLoopService.execute(...)`.
2. **Current Implementation Status**: 
   - The closed loop is fully implemented as an internal Python orchestration service (`ClosedLoopService`).
   - It is **not yet exposed as an active REST API route** (the legacy endpoint `POST /api/v1/remediations/apply` references an obsolete method name `RemediationService.remediate`).
   - A live PostgreSQL 17 container with `hypopg` and loaded seed data is required to physically execute the loop and generate real benchmark timings.
3. **Data Authenticity Status**: 
   - No real measured cases currently exist in the repository; all existing cases in `research/data/sample_cases.json` are synthetic/simulated.
   - The framework for measuring and recording real cases is validated and ready for controlled execution in subsequent steps.

---

## 2. Complete Closed-Loop Trace

The complete end-to-end execution path from raw query to verified historical memory is traced below:

```
                      1. Read-Only Query / Workload
                                   ↓
                     2. DatabaseMonitorService.explain_query
                                   ↓ (raw EXPLAIN JSON plan)
                     3. PlanAnalyzer.analyze & BottleneckDetector.detect
                                   ↓ (detected BottleneckFinding list)
                     4. IntelligenceService._evaluate_candidates
                                   ↓ (deterministic candidate definitions)
                     5. HypoPGValidatorService.validate_candidate
                                   ↓ (counterfactual cost improvement)
                     6. RecommendationEngine.recommend & SafetyAssessor.assess
                                   ↓ (SafetyAssessment: eligible_for_approval)
                     7. ApprovalService.create_approval_request & approve
                                   ↓ (ApprovalRequest: status=APPROVED)
                     8. RemediationService.apply_approved_recommendation
                                   ↓ (CREATE INDEX DDL executed & verified in pg_indexes)
                     9. BenchmarkService.benchmark
                                   ↓ (EXPLAIN ANALYZE before/after execution measurements)
                    10. ClosedLoopService._save_memory / MemoryService.create_memory
                                   ↓
                   11. OptimizationMemoryModel (PostgreSQL Database)
                       [provenance=MEASURED, is_verified=True, verification_state=VERIFIED_MEASURED]
```

### Stage-by-Stage Trace Details

| Stage | Module & Function | Input | Output | Validations & Invariants | Downstream Information Recorded |
|---|---|---|---|---|---|
| **1. Query Execution Plan** | `DatabaseMonitorService.explain_query` | `query: str` | `ExplainResult(plan, query)` | Rejects empty strings; executes `EXPLAIN (FORMAT JSON)` | Query text, raw planner tree |
| **2. Finding Detection** | `PlanAnalyzer.analyze`<br>`BottleneckDetector.detect` | `raw_plan: Dict` | `List[BottleneckFinding]` | Checks node types (`Seq Scan`, `Sort`, `Nested Loop`), cost thresholds, filter selectivity | Bottleneck type, table, filter predicates, estimated rows/costs |
| **3. Candidate Generation** | `IntelligenceService._evaluate_candidates` | `findings: List[BottleneckFinding]`, `query: str` | `List[CandidateEvaluation]` | Extracts valid columns from predicates; generates baseline multi-column and single-column candidates; deduplicates via canonical key | `candidate_id`, `is_baseline`, canonical `(table, method, cols)` |
| **4. HypoPG Validation** | `HypoPGValidatorService.validate_candidate` | `HypotheticalIndexRequest` | `HypoPGValidationResult` | Identifier regex sanitization; session-scoped `hypopg_create_index`; guaranteed `hypopg_reset` in finally block | `cost_improvement_percent`, `hypothetical_cost`, plan changes |
| **5. Safety Assessment** | `SafetyAssessor.assess` | `OptimizationRecommendation` | `SafetyAssessment` | 7 deterministic checks (status, HypoPG validation, cost improvement $\ge 15\%$, risk tier, SQL preview sanitization) | `eligible_for_approval: bool`, `blocking_reasons`, `safety_level` |
| **6. Human Approval** | `ApprovalService.create_approval_request`<br>`ApprovalService.approve` | `recommendation`, `safety_assessment`, `approved_by: str` | `ApprovalRequest` | Fails closed if ineligible; requires non-empty `approved_by`; enforces expiration timeout; zero DDL executed | `approval_id`, `status=APPROVED`, `approved_by`, timestamps |
| **7. Physical Remediation** | `RemediationService.apply_approved_recommendation` | `ApprovalRequest`, `current_recommendation` | `RemediationResult` | Authorization re-check; snapshot integrity check; safety re-evaluation; idempotency check in `pg_indexes`; deterministic index naming; atomic DDL execution; post-creation verification in `pg_indexes` | `remediation_id`, `sql_executed`, `index_name`, `target_relation`, `target_columns`, `verification_passed=True` |
| **8. Runtime Benchmark** | `BenchmarkService.benchmark` | `query: str`, `remediation: RemediationResult` | `BenchmarkResult` | Read-only SQL safety validator; remediation authorization check (`status=APPLIED`, `verification_passed=True`); runs $N$ measurements + $W$ warmups; separates planner vs runtime metrics | `benchmark_id`, `before` & `after` `ExecutionMeasurement` (mean, median, stddev ms, buffer blocks), `runtime_improvement_percent` |
| **9. Memory Persistence** | `ClosedLoopService.execute`<br>`MemoryService.create_memory` | Benchmark, remediation, approval, diagnosis records | `OptimizationMemory` | Enforces strict provenance rules: `is_verified=True` and `verification_state=VERIFIED_MEASURED` only when benchmark completed and remediation verified | Persisted row in `optimization_memories` table with 1536-dim vector embedding |

---

## 3. Benchmark Measurement Audit

`BenchmarkService` governs controlled execution benchmarking via PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`.

### Measurement Mechanics
- **Primary Metric**: PostgreSQL actual Execution Time in milliseconds (`execution_time_ms`).
- **Repetitions & Warm-up**:
  - `BENCHMARK_RUNS` (default: 10 repetitions).
  - `BENCHMARK_WARMUP_RUNS` (default: 2 repetitions, executed and discarded to eliminate cold-cache anomalies).
- **Statistical Outputs**:
  - `mean_execution_time_ms`, `median_execution_time_ms`, `min_execution_time_ms`, `max_execution_time_ms`, `stddev_execution_time_ms`, `coefficient_of_variation` ($\frac{\text{stddev}}{\text{mean}}$).
  - Planning time (`planning_time_ms`), row count (`rows_returned`), shared buffer hits/reads (`shared_hit_blocks`, `shared_read_blocks`), and plan tree nodes.
- **Before vs. After Baseline Methodology**:
  - *Post-Remediation Physical State*: The physical index exists on the database table.
  - *Controlled Baseline ("Before")*: Executed within a dedicated transaction with `SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off;` to simulate the pre-index plan without destructive index drops.
  - *Remediated Evaluation ("After")*: Executed within a transaction with `SET LOCAL enable_indexscan = on; SET LOCAL enable_bitmapscan = on;`.
  - *Relative Delta Calculation*:
    $$\Delta = \frac{T_{\text{before}} - T_{\text{after}}}{T_{\text{before}}}$$
    $$\text{runtime\_improvement\_percent} = \Delta \times 100.0$$
- **Usability for Research**:
  - Both $T_{\text{before}}$ (`before.mean_execution_time_ms`) and $T_{\text{after}}$ (`after.mean_execution_time_ms`) are recorded as positive floating-point millisecond values.
  - Usable directly by Phase 4 `CandidateSelector.select_outcome_aware`.

---

## 4. Physical Remediation Audit

`RemediationService` executes actual schema mutations on PostgreSQL.

### Key Operational Characteristics
1. **Deterministic Index Generation**:
   - Name pattern: `idx_autodba_<table_name>_<col1>_<col2>` (truncated with MD5 hash suffix to 63 bytes if length exceeds PostgreSQL identifier limits).
   - SQL pattern: `CREATE INDEX <index_name> ON <table_name> (<col1>, <col2>);`.
2. **Candidate Fidelity**:
   - The SQL is generated strictly from the approved `relation` and `columns` in `OptimizationRecommendation`.
   - Never accepts or executes raw unvalidated SQL strings.
3. **Idempotency & Collision Protection**:
   - Queries `pg_indexes` before executing DDL.
   - If an equivalent index on `(table, columns)` exists, returns `status = ALREADY_APPLIED` without error.
4. **Safety & Verification**:
   - DDL executes in an explicit transactional block (`with engine.begin()`).
   - Post-DDL verification inspects `pg_indexes` to confirm that the index is physically present and covers the exact columns in order.
5. **HypoPG vs. Physical Separation**:
   - Confirmed: HypoPG simulation (`HypoPGValidatorService`) only creates in-memory simulated objects via `hypopg_create_index()` and immediately resets them with `hypopg_reset()`.
   - HypoPG simulation does **not** write to disk, does **not** update `pg_indexes`, and is **never** treated as a measured physical outcome.

---

## 5. Human Approval Boundary

AutoDBA enforces a strict, auditable boundary between automated diagnosis and physical schema changes:
1. **Creation Gate**: An `ApprovalRequest` can only be created if `SafetyAssessment.eligible_for_approval == True`.
2. **Human Interaction**: The approval transition requires an explicit external actor (`approved_by: str`). Anonymous or blank approvals are rejected with `ValueError`.
3. **Temporal Invalidation**: Requests have an expiration window (`APPROVAL_EXPIRATION_MINUTES`, default 60 min). Expired requests transition to `EXPIRED` and cannot be remediated.
4. **No Auto-Remediation**: The `ApprovalService` has zero database write handles. It creates audit records only. Physical DDL is only initiated when `ClosedLoopService` or `RemediationService` is explicitly invoked with an approved request ID.

---

## 6. Closed-Loop Memory Eligibility Conditions

In `ClosedLoopService.execute`, a record is marked verified if and only if all of the following conditions hold:

```python
is_verified = (
    benchmark.status.value == "completed"
    and remediation.status.value in ("applied", "already_applied")
    and remediation.verification_passed
)
provenance = CaseProvenance.MEASURED if is_verified else CaseProvenance.UNVERIFIED
verification_state = (
    OutcomeVerificationState.VERIFIED_MEASURED
    if is_verified
    else OutcomeVerificationState.UNVERIFIED
)
```

### Complete Invariant Checklist for `VERIFIED_MEASURED`
- [x] Remediation status is `APPLIED` or `ALREADY_APPLIED`.
- [x] Post-remediation index verification confirmed index in `pg_indexes` (`verification_passed == True`).
- [x] Benchmark execution succeeded without database exceptions (`status == COMPLETED`).
- [x] Provenance is explicitly `CaseProvenance.MEASURED`.
- [x] Verification state is explicitly `OutcomeVerificationState.VERIFIED_MEASURED`.
- [x] `is_verified` flag is `True`.

### Fields Stored in `OptimizationMemoryModel`
1. **Matching Identifiers**: `recommendation` JSON stores `{"relation": table, "columns": [cols], "index_method": "btree"}` $\rightarrow$ directly convertible to canonical key `(table, index_method, tuple(cols))`.
2. **Timing Benchmarks**: `benchmark` JSON stores `before.mean_execution_time_ms`, `after.mean_execution_time_ms`, `runtime_improvement_percent`.
3. **Provenance & Verification**: `provenance = "measured"`, `is_verified = True`, `verification_state = "verified_measured"`.
4. **Diagnosis Context**: `diagnosis` JSON, `query_text`, `query_fingerprint`, and vector `embedding`.

---

## 7. Database and Environment Requirements

Running legitimate closed-loop executions requires the following environment:
1. **PostgreSQL 17 Instance**:
   - `postgres:17` with `postgresql-17-hypopg` extension installed.
   - `pg_stat_statements` enabled in `postgresql.conf` (`shared_preload_libraries = 'pg_stat_statements'`).
2. **Initialization SQL Scripts**:
   - `01-init.sql`: Creates `customers`, `products`, `orders`, `order_items` tables and baseline foreign keys.
   - `02-seed.sql`: Seeds 500 customers, 100 products, 5,000 orders, and 15,000 order items with statistical `ANALYZE`.
   - `03-intelligence.sql`: Creates `optimization_memories` table with vector embedding columns and indexes.
   - `04-intelligence-provenance-migration.sql`: Adds `provenance`, `is_verified`, and `verification_state` columns.
3. **Application Services**:
   - FastAPI application engine configured via `DATABASE_URL` (`postgresql+psycopg://autodba:autodba@localhost:5432/autodba`).

---

## 8. Measured-Data Feasibility

| Question | Assessment & Code Findings |
|---|---|
| **A. Can one legitimate measured case be produced?** | **YES**. Executing the closed loop on query `SELECT * FROM orders WHERE customer_id = 42` creates `idx_autodba_orders_customer_id`, benchmarks sequential scan vs index scan on 5,000 rows, and writes a verified memory record. |
| **B. Can multiple independent measured cases be produced?** | **YES**, across different tables (`orders`, `products`, `order_items`, `customers`), single and multi-column filter predicates, and join conditions. |
| **C. What is the smallest experimental workload capable of producing them?** | The standard seed database (`02-seed.sql`) containing 5,000 orders and 15,000 order items is sufficient to show measurable differences between Seq Scan and Index Scan. |
| **D. What variations create distinct query templates?** | 1. Single-column equality: `SELECT * FROM orders WHERE customer_id = ?`<br>2. Multi-column equality: `SELECT * FROM orders WHERE customer_id = ? AND status = ?`<br>3. Range query: `SELECT * FROM orders WHERE total_amount > ?`<br>4. Foreign key join: `SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.email = ?`<br>5. Aggregation grouping: `SELECT customer_id, count(*) FROM orders WHERE status = ? GROUP BY customer_id` |
| **E. What must be recorded for every case?** | Canonical query, canonical template hash, plan tree, candidate index definition, HypoPG cost improvement, $T_{\text{before}}$, $T_{\text{after}}$, relative speedup $\Delta$, verification flags, and provenance metadata. |
| **F. What risks could contaminate the evaluation?** | Template overlap between train/test, lingering physical indexes altering subsequent query plans, and buffer pool thermal caching effects. |

---

## 9. Experimental Contamination Risks & Mitigations

To maintain rigorous scientific validity, the following contamination risks must be addressed prior to conducting benchmark experiments:

### 1. Persistent Physical Index State Contamination
- **Risk**: Creating an index `idx_autodba_orders_customer_id` during Case 1 permanently modifies the database schema. If Case 2 tests `orders` with `customer_id` and `status`, it will use Case 1's index instead of running a clean unindexed baseline.
- **Required Mitigation**: After each closed-loop case execution and benchmark recording, the created index must be dropped (`DROP INDEX <index_name>`) or the database schema restored to a clean snapshot before the next case is executed.

### 2. Buffer Pool and Page Cache Warmth
- **Risk**: Running 10 warmup + measurement iterations for Case 1 leaves table pages resident in PostgreSQL `shared_buffers` and OS filesystem cache, giving Case 2 artificially low execution times.
- **Required Mitigation**: Discard explicit warm-up runs for each query and report statistical spread (stddev, CV). For cross-workload isolation, run `DISCARD ALL` between runs.

### 3. Template Group Partition Leakage
- **Risk**: If training memory contains cases generated from the same template hash as the held-out test set, Policy B and Policy C will be evaluated on memorized query patterns rather than unseen patterns.
- **Required Mitigation**: Enforce `grouped_template_split()` from Phase 3 so that the set of templates in TRAIN and TEST are strictly disjoint:
  $$\text{Templates}(\text{Train}) \cap \text{Templates}(\text{Test}) = \emptyset$$

---

## 10. Safety & Isolation Requirements

For all future empirical data generation:
1. **Dedicated Disposable Database**: Must use an isolated containerized PostgreSQL instance. Never connect to staging or production databases.
2. **Reversible Mutations**: Every index creation must be cataloged and paired with an automated teardown routine.
3. **Preserved Approval Boundary**: Benchmark harnesses must not bypass the approval service; they should programmatically simulate explicit human approval (`approved_by="research_harness"`) through the authoritative `ApprovalService.approve` interface.

---

## 11. Exact Minimum Path to First Legitimate Measured Case

To produce the very first verified `MEASURED` historical case:
1. **Start Environment**: Launch PostgreSQL 17 container with seed database loaded (`docker-compose up -d postgres`).
2. **Run Query Diagnosis**:
   ```python
   query = "SELECT * FROM orders WHERE customer_id = 42;"
   diag_resp = intelligence_service.diagnose(request=DiagnoseRequest(query=query))
   cand = diag_resp.diagnosis.candidate_evaluations[0]
   ```
3. **Submit & Approve Request**:
   ```python
   appr_req = approval_service.create_approval_request(cand.recommendation)
   approved = approval_service.approve(appr_req.approval_id, approved_by="research_evaluator")
   ```
4. **Execute Closed Loop**:
   ```python
   closed_loop = ClosedLoopService(db_session)
   result = closed_loop.execute(
       approval_id=approved.approval_id,
       query_text=query,
       incident_type="missing_index",
       diagnosis=diag_resp.diagnosis.analysis,
       recommendation=approved.recommendation,
   )
   ```
5. **Verify Recorded Memory**:
   - Inspect `result["memory"]`.
   - Confirm `provenance == CaseProvenance.MEASURED`.
   - Confirm `is_verified == True`.
   - Confirm `verification_state == OutcomeVerificationState.VERIFIED_MEASURED`.
   - Confirm `benchmark["runtime_improvement_percent"]` is populated with real execution timings.

---

## 12. Data Fields Required for the Eventual Research Corpus

When building the multi-case evaluation corpus (`research/data/measured_cases.json`), each case must contain:
1. `case_id`: Unique deterministic identifier (e.g. `case_measured_orders_001`).
2. `incident_type`: e.g. `missing_index`.
3. `query`: `text`, canonical `template`, `template_hash`.
4. `plan`: `estimated_cost`, `scan_type`, `actual_rows`.
5. `recommendation`: `table`, `columns`, `index_method`, `sql_preview`.
6. `hypopg_validation`: `hypopg_validated`, `cost_improvement_percent`.
7. `measured_outcome`: `before_runtime_ms`, `after_runtime_ms`, `runtime_improvement_percent`, `measurement_runs`, `benchmark_status`.
8. `measurement_quality`: `runs_executed`, `warmup_runs_discarded`, `coefficient_of_variation`.
9. `provenance`: `real_measured` (`measured`).
10. `is_verified`: `True`.
11. `verification_state`: `verified_measured`.

---

## 13. Current Blockers

1. **Environment Execution State**:
   - Docker and PostgreSQL 17 services are not actively running during this static audit step.
2. **API Endpoint Wiring**:
   - `POST /api/v1/remediations/apply` has a broken call to `RemediationService.remediate`. A dedicated closed-loop execution endpoint or test script runner is needed for automated collection.
3. **Schema Reset Scaffolding**:
   - A fixture/helper to automatically reset physical database indexes between case runs is needed to prevent cross-case index contamination during batch collection.

---

## 14. Recommended Next Step

**Phase 5B — Controlled Closed-Loop Scaffolding & Seed Benchmark Runner**:
1. Implement a clean, dedicated research runner script (`research/collect_measured_cases.py`) that:
   - Connects to the local PostgreSQL test instance.
   - Executes the closed loop across a set of diverse query templates.
   - Automatically drops created indexes between runs to guarantee clean baseline conditions.
   - Exports the resulting verified measured records directly into `research/data/measured_cases.json`.
2. Do not modify production application code or baseline files.
