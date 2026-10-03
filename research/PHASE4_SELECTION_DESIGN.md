# Phase 4 Design Document: Candidate Selection Policies & Outcome-Aware Ranking

**Location:** `research/PHASE4_SELECTION_DESIGN.md`  
**Workspace:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Date:** 2026-10-01  
**Status:** Design & Architectural Audit (Read-Only — No Production Code Changes)  

---

## 1. Research Question

> *"For unseen PostgreSQL query patterns, does using benchmarked historical cases to rank deterministic, safety-validated candidate recommendations improve measured outcomes over a planner-only baseline, without increasing unsafe or regressive recommendations?"*

### Research Scope & Trust Boundary:
Historical memory must **never** synthesize arbitrary or unvalidated index recommendations. Candidate generation is strictly governed by the deterministic Phase 1 pipeline (`RecommendationEngine` + `HypoPGValidator` + `SafetyAssessor`). Historical evidence is used **exclusively** to rank and select among candidates that have already passed counterfactual validation and safety assessment.

---

## 2. Current Candidate Representation (Phase 1 Audit)

In Phase 1 ([backend/app/services/intelligence_service.py](file:///C:/Users/swarsh/Desktop/autodba-research/autodba-main/backend/app/services/intelligence_service.py#L156-L243)), candidates are generated per bottleneck finding and encapsulated in [`CandidateEvaluation`](file:///C:/Users/swarsh/Desktop/autodba-research/autodba-main/backend/app/schemas/optimization.py):

```python
class CandidateEvaluation(BaseModel):
    candidate_id: str                      # Deterministic ID: f"cand_{table}_{col_suffix}"
    recommendation: OptimizationRecommendation
    validation: ValidationResult           # HypoPG counterfactual simulation
    safety_assessment: SafetyAssessment    # Safety level and approval requirements
    is_baseline: bool                      # True for original finding candidate, False for alternatives
```

### Exact Fields Available per Candidate:
1. **Target Identity:** `target_table: str`, `target_columns: List[str]`, `index_method: IndexMethod` (default `BTREE`).
2. **Action SQL:** `action: str` (e.g. `CREATE INDEX ON orders (customer_id);`).
3. **HypoPG Counterfactual Evidence (`ValidationResult`):**
   - `verdict: ValidationVerdict` (`VALIDATED`, `REJECTED`, `INCONCLUSIVE`, `SIMULATION_ERROR`)
   - `cost_improvement_percent: float` ($100 \times (C_{\text{before}} - C_{\text{hypo}}) / C_{\text{before}}$)
   - `original_cost: float`, `hypothetical_cost: float`
   - `original_root_node_type: str`, `hypothetical_root_node_type: str`
   - `original_scan_type: str`, `hypothetical_scan_type: str`
4. **Safety & Risk (`SafetyAssessment`):**
   - `safety_level: SafetyLevel` (`SAFE`, `LOW_RISK`, `MEDIUM_RISK`, `HIGH_RISK`)
   - `requires_approval: bool`
   - `reasons: List[str]`, `warnings: List[str]`
5. **Baseline Marker:** `is_baseline: bool` (identifies the primary recommendation chosen by the existing planner baseline).

---

## 3. Current Historical Outcome Representation (Phase 2 Audit)

In Phase 2 ([backend/app/services/memory_service.py](file:///C:/Users/swarsh/Desktop/autodba-research/autodba-main/backend/app/services/memory_service.py) and [research/case_schema.py](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py)), historical optimization cases record:

```python
class OptimizationCase:
    case_id: str
    incident_type: IncidentType
    query: QueryInfo                       # text, canonical_template, template_hash
    plan: PlanInfo                         # cost, scan_type, root_node, findings
    recommendation: RecommendationAction   # action_type, table, columns, index_method, sql_preview
    hypopg_validation: HypoPGValidation   # validated, cost_before, cost_after, improvement_pct
    measured_outcome: MeasuredOutcome     # before/after runtime ms, improvement_pct, plan_changed
    measurement_quality: MeasurementQualityInfo
    provenance: CaseProvenance             # MEASURED, SEEDED, SYNTHETIC, UNVERIFIED
    is_verified: bool                      # True ONLY for real closed-loop benchmark runs
    verification_state: str                # verified_measured, synthetic, unverified
```

### Exact Measured Benchmark Fields:
- `before_runtime_ms: float`, `after_runtime_ms: float`
- `runtime_improvement_percent: float` ($100 \times (T_{\text{before}} - T_{\text{after}}) / T_{\text{before}}$)
- `planner_cost_improvement_percent: float`
- `plan_changed: bool`, `index_used_before: bool`, `index_used_after: bool`
- `measurement_runs: int`, `benchmark_status: str`

### Candidate Linkage in Historical Memory:
The historical `recommendation` structure stores: `table`, `columns` (ordered list), and `index_method`. This enables exact mapping between a current candidate and historical cases via a shared canonical index key.

---

## 4. Policy A — Planner-Only Baseline

### Definition:
Selects the existing Phase 1 planner/default candidate directly identified by `CandidateEvaluation.is_baseline == True`.

### Formal Rules:
1. Identify candidate $c_{\text{baseline}} \in \mathcal{C}_{\text{candidates}}$ where $c_{\text{baseline}}.\text{is\_baseline} == \text{True}$.
2. Output $c_{\text{baseline}}$ as the selected recommendation.
3. **Historical Data Used:** **None.** (Zero historical memory access, zero RAG retrieval).
4. **Semantics:** Preserves the exact deterministic recommendation produced by `IntelligenceService.diagnose()`.

---

## 5. Policy B — Similarity-Based Historical Retrieval

### Definition:
Ranks candidates within the Phase 1 candidate pool using historical cases retrieved from the leakage-safe `TRAIN` corpus based on query token similarity, **without** conditioning on whether the historical case was an empirical success or regression.

### Selection Rule:
1. Filter the Phase 1 candidate pool $\mathcal{C}_{\text{candidates}}$ to those meeting safety and HypoPG validation criteria ($\mathcal{C}_{\text{safe}}$).
2. Retrieve top-$K$ cases $\mathcal{H}_{\text{train}}$ from the `TRAIN` partition using baseline token-hash similarity $\text{sim}(Q_{\text{test}}, h)$.
3. For each candidate $c \in \mathcal{C}_{\text{safe}}$, compute its similarity support from retrieved cases whose index definition matches $c$:
   $$S_{\text{sim}}(c) = \sum_{h \in \mathcal{H}_{\text{train}} \mid \kappa(h) = \kappa(c)} \text{sim}(Q_{\text{test}}, h)$$
4. Rank candidates by:
   $$\text{Score}_B(c) = \text{HypoPG\_Cost\_Improvement}(c) + \alpha \cdot S_{\text{sim}}(c)$$
   (where $\alpha$ is a scaling hyperparameter).
5. Select the candidate with the highest $\text{Score}_B(c)$.
6. **Key Constraint:** Policy B can **never** introduce or select candidates outside the Phase 1 candidate pool $\mathcal{C}_{\text{candidates}}$.

---

## 6. Policy C — Outcome-Aware Historical Selection

### Definition:
Ranks candidates within the Phase 1 safe candidate pool using **verified empirical benchmark outcomes** (`provenance=MEASURED`, `is_verified=True`, `verification_state=VERIFIED_MEASURED`) from the leakage-safe `TRAIN` corpus.

### Selection Rule:
1. Filter the Phase 1 candidate pool to safe, validated candidates $\mathcal{C}_{\text{safe}}$.
2. Retrieve verified historical cases $\mathcal{H}_{\text{verified}} \subseteq \mathcal{H}_{\text{train}}$ where `is_verified == True`.
3. For each candidate $c \in \mathcal{C}_{\text{safe}}$, compute its empirical outcome support:
   $$S_{\text{outcome}}(c) = \sum_{h \in \mathcal{H}_{\text{verified}} \mid \kappa(h) = \kappa(c)} \text{sim}(Q_{\text{test}}, h) \cdot \omega(h)$$
   where $\omega(h)$ is the outcome signal derived from historical execution:
   $$\omega(h) = \begin{cases} 
   +\Delta_{\text{runtime}}(h) & \text{if } \Delta_{\text{runtime}}(h) \ge 0 \\
   -\lambda_{\text{reg}} \cdot |\Delta_{\text{runtime}}(h)| & \text{if } \Delta_{\text{runtime}}(h) < 0 
   \end{cases}$$
4. Rank candidates by:
   $$\text{Score}_C(c) = \text{HypoPG\_Cost\_Improvement}(c) + \beta \cdot S_{\text{outcome}}(c)$$
5. Select the candidate with the highest $\text{Score}_C(c)$.
6. **Key Constraints:**
   - Unverified, seeded, or synthetic historical cases contribute $\omega(h) = 0$.
   - Policy C can **never** select candidates outside the Phase 1 candidate pool $\mathcal{C}_{\text{candidates}}$.

---

## 7. Treatment of the Regression Penalty ($\lambda_{\text{reg}}$)

- **Nature of $\lambda_{\text{reg}}$:** The regression penalty $\lambda_{\text{reg}}$ is an **experimental design parameter (hyperparameter)** representing the degree of risk aversion against performance regressions.
- **Unweighted Baseline:** $\lambda_{\text{reg}} = 1.0$ treats positive speedups and negative regressions symmetrically.
- **Asymmetric Ablation:** $\lambda_{\text{reg}} > 1.0$ penalizes historical regressions more severely than equivalent speedups.
- **Hyperparameter Discipline:** Any tuning or calibration of $\lambda_{\text{reg}}$ must be performed **strictly on training/development splits**. The held-out `TEST` partition must **never** be used to select or tune $\lambda_{\text{reg}}$.

---

## 8. Outcome Representation & Normalization

### Relative Runtime Improvement Definition:
Measured outcome improvement for a historical case $h$ is defined as the relative execution time delta between pre-remediation and post-remediation benchmarks:

$$\Delta_{\text{runtime}} = \frac{T_{\text{before}} - T_{\text{after}}}{T_{\text{before}}}$$

### Mathematical Properties:
- $\Delta_{\text{runtime}} > 0$: Performance improved ($T_{\text{after}} < T_{\text{before}}$). Upper bounded by $1.0$ (as $T_{\text{after}} \to 0$).
- $\Delta_{\text{runtime}} = 0$: No performance change ($T_{\text{after}} = T_{\text{before}}$).
- $\Delta_{\text{runtime}} < 0$: Performance regressed ($T_{\text{after}} > T_{\text{before}}$). Unbounded below (as $T_{\text{after}} \to \infty$).

### Handling Noise and Outliers:
- **Measurement Aggregation:** $T_{\text{before}}$ and $T_{\text{after}}$ represent arithmetic mean execution times across repeated runs (`ExecutionMeasurement.mean_execution_time_ms`).
- **Winsorization / Bounding:** To prevent a single extreme query timeout from dominating the linear scoring function, an experimental clipping bound (e.g. $\Delta_{\text{runtime}} \ge -2.0$) can be evaluated as an ablation parameter during development.

---

## 9. Candidate ↔ Historical Case Matching Rule

### Canonical Index Key:
Matching between a current candidate $c$ and a historical recommendation $h$ is defined by the canonical tuple:

$$\kappa = \left( \text{table.strip().lower()}, \; \text{index\_method.strip().lower()}, \; \text{tuple}(col\text{.strip().lower() for } col \in \text{columns}) \right)$$

### Scope and Exact Applicability:
- **Scope Limitation:** AutoDBA currently generates **only standard single-column and multi-column B-tree secondary index recommendations** (`CREATE INDEX ON <table> (<cols>);`).
- **Column Sequence:** In PostgreSQL B-tree composite indexes, column ordering is semantically significant for prefix indexing. Therefore, $\text{tuple}(\text{columns})$ preserves exact column order.
- **Unsupported Constructs:** AutoDBA's `RecommendationEngine` does not currently generate partial indexes (`WHERE ...`), expression indexes, or included columns (`INCLUDE (...)`). The research claim and matching rule are strictly scoped to standard B-tree index definitions.

---

## 10. Abstention & No-Evidence Fallback

When evaluating candidate set $\mathcal{C}_{\text{candidates}}$ on test query $Q_{\text{test}}$:
- If no matching historical cases exist ($\mathcal{H}_{\text{matched}}(c) = \emptyset$),
- If all matching cases are `SEEDED`, `SYNTHETIC`, or `UNVERIFIED`, or
- If historical similarity is below threshold ($\text{sim} < \theta_{\text{min}}$):

$$S_{\text{outcome}}(c) = 0.0 \implies \text{Score}_C(c) \equiv \text{Score}_A(c)$$

### Scientifically Defensible Fallback Statement:
> *"When no eligible measured historical evidence exists, the outcome-aware selection policy falls back to the planner-only baseline selection. This defines a deterministic no-history fallback, but does not guarantee a non-regressive physical benchmark outcome."*

---

## 11. Safety Boundary Enforcement

```
Raw Query + Incident Finding
              │
              ▼
┌────────────────────────────────────────┐
│ Phase 1 Candidate Generation           │
│ (Deterministic candidate pool)         │
└────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ HypoPG Counterfactual Simulation       │
│ (Disqualifies REJECTED candidates)     │
└────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ SafetyAssessor Eligibility Check       │
│ (Enforces SAFE / LOW_RISK bounds)      │
└────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ Phase 4 Policy Selection (A, B, or C)  │
│ (Ranks among SAFE candidates ONLY)     │
└────────────────────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ Human Approval & Remediation Engine    │
│ (Pre-execution gate & verification)    │
└────────────────────────────────────────┘
```

**Architectural Guarantee:** Policy selection occurs **downstream** of HypoPG and SafetyAssessor, and **upstream** of Human Approval. Historical ranking can neither approve an unsafe recommendation nor execute DDL directly.

---

## 12. Experimental Comparison Protocol

The three policies will be evaluated across unseen query patterns in the `TEST` partition:

| Metric | Definition | Research Hypothesis Evaluated |
| :--- | :--- | :--- |
| **Mean Runtime Improvement ($\Delta_{\text{runtime}}$)** | Average measured relative runtime reduction after executing the selected candidate. | Does Policy C achieve higher execution speedups than Policy A on unseen queries? |
| **Regression Rate (%)** | Percentage of selected recommendations causing $\Delta_{\text{runtime}} < 0$. | Does Policy C reduce or eliminate regressions compared to Policy A & B? |
| **Unsafe Recommendation Rate (%)** | Rate of recommendations flagged as unsafe or failing post-remediation verification. | Does Policy C maintain a 0% unsafe rate? |
| **Baseline Override Frequency (%)** | Percentage of test queries where Policy C selects an alternative candidate over $c_{\text{baseline}}$. | When Policy C overrides the planner, is the empirical outcome superior? |

---

## 13. Required Data & Gaps

### Current Data Status:
Inspection of [`research/data/sample_cases.json`](file:///C:/Users/swarsh/Desktop/autodba-research/research/data/sample_cases.json) shows:
- Total cases: **4**
- `SEEDED` cases: 2 (`seed-001`, `seed-002`)
- `SIMULATED` cases: 2 (`sim-001`, `sim-002`)
- `REAL_MEASURED` cases: **0**

### Data Prerequisite:
To evaluate Policy C empirically, a benchmark workload execution suite must generate a corpus of real closed-loop `MEASURED` cases (`is_verified=True`) with genuine pgbench timing measurements before and after index creation.

---

## 14. Minimal Phase 4 Implementation Plan

1. **Implement Canonical Candidate Key:** Add `canonical_candidate_key(recommendation)` in `research/case_schema.py`.
2. **Implement Policy Evaluators in Research Harness:** Implement Policy A, B, and C candidate scorers in `research/evaluation_harness.py`.
3. **Generate Measured Benchmark Corpus:** Execute closed-loop benchmark runs to populate verified historical cases.
4. **Execute Policy Comparison:** Run full evaluation comparing Policy A, B, and C on the leakage-safe test split.

---

## 15. Things Explicitly NOT to Implement Yet

- **DO NOT** modify backend application code (`autodba-main/backend/app/`).
- **DO NOT** alter production `IntelligenceService.diagnose()`.
- **DO NOT** implement LLM-based candidate selection.
- **DO NOT** execute benchmarks or create artificial test metrics.
- **DO NOT** commit until design review is complete.
