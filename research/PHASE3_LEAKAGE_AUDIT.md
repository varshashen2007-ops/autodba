# Phase 3 Research Audit: Leakage-Safe Evaluation Foundation

**Location:** `research/PHASE3_LEAKAGE_AUDIT.md`  
**Workspace:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Baseline Commit:** `4b92f1cd80b4f6dbe4f14b584bef5a714feffa06`  
**Date:** 2026-10-01  

---

## 1. Executive Finding

**Verdict:** The pre-existing research evaluation scaffolding in `research/` is **scientifically invalid, logically disconnected, and unexecutable in its current state**.

The research question under investigation is:
> *"For unseen PostgreSQL query patterns, does using benchmarked historical cases to rank deterministic, safety-validated candidate recommendations improve measured outcomes over a planner-only baseline, without increasing unsafe or regressive recommendations?"*

Evaluating generalization to "unseen query patterns" requires that:
1. Query templates in the test split never appear in the training/history split.
2. The retrieval candidate pool available during test evaluation consists **exclusively** of training/history cases.
3. Feature representations (embeddings) are deterministic and reproducible.
4. Evaluation measures real physical execution metrics without mock data or outcome leakage.

The audit revealed that the existing `research/` scaffolding violates every single one of these criteria:
- `stratified_split()` explicitly splits identical query templates 50/50 across train and test (guaranteed template leakage).
- `BaselineRetrievalMethods` searches the full case pool rather than restricting candidate retrieval to the train set (retrieval leakage).
- `case_schema.py` fails to define `OptimizationCase`, causing immediate `ImportError` crashes across all research scripts.
- Vector embeddings in `baseline_retrieval.py` rely on Python's non-deterministic built-in `hash()` rather than cryptographic token hashing.
- `evaluation_framework.py` and `harness.py` simulate benchmark outcomes using hardcoded string matching (`"customer_id" in recommendation.lower()`) rather than evaluating actual measured cases.

---

## 2. Current Evaluation Architecture

The `research/` directory contains a standalone set of scripts separate from `autodba-main/`:

| Module | Purported Purpose | Actual State |
| :--- | :--- | :--- |
| `case_schema.py` | Canonical dataclass schemas for historical optimization cases. | Incomplete: `OptimizationCase` class is missing; helper functions reference undefined types. |
| `split_strategy.py` | Grouped/stratified train/test splitting to prevent leakage. | Broken & Leaky: `stratified_split` splits identical query templates into both train and test. |
| `baseline_retrieval.py` | Lexical, dense, hybrid, and outcome-aware retrieval baselines. | Broken: Uses randomized `hash()`; searches the entire dataset without train/test isolation. |
| `evaluation_harness.py` | Orchestrates evaluation across baselines and computes metrics. | Unexecutable: Type mismatches on `TrainTestSplit`; treats uncallable classes as callables; metric computation is `TODO`. |
| `evaluation_framework.py` | Evaluates single queries against ground truth. | Mocked: Returns hardcoded mock data and simulated heuristic benchmarks. |
| `harness.py` | CLI comparison between AutoDBA and manual intervention. | Mocked: Simulates manual DBA choices and benchmark improvements with hardcoded constants. |
| `ablation_study.py` | Isolates contributions of plan features, context, and outcomes. | Stub: Returns hardcoded summary strings with no metric execution. |
| `data/sample_cases.json` | 4 sample cases (`seed-001`, `seed-002`, `sim-001`, `sim-002`). | Minimal static JSON fixture without verified physical benchmark traces. |

---

## 3. Exact Leakage Risks Found

### A. Query / Template Leakage (Severe)
- Queries sharing the exact same SQL template, AST structure, or query fingerprint are distributed evenly across both training and test splits.
- Evaluating a test case whose template already exists in training memory tests *memorization of known query shapes*, not *generalization to unseen query patterns*.

### B. Case / Instance Leakage (Severe)
- Multiple execution runs of the same query pattern (e.g. `seed-001` and subsequent closed-loop runs on `orders(customer_id)`) are partitioned by index rather than by query template group.
- Variations with different literal values (e.g. `WHERE customer_id = 42` vs `WHERE customer_id = 99`) are not mapped to a shared group key and cross split boundaries.

### C. Retrieval Leakage (Severe)
- The retrieval index (`BaselineRetrievalMethods`) is initialized with `self.cases` (the full dataset including test cases).
- During test query evaluation, `current_autodba_retrieval()` only checks `if case.case_id == query_case.case_id: continue`.
- As a result, the test query can retrieve:
  - Other test cases from the test split.
  - Historical instances of its own query template.

### D. Label / Outcome Leakage (High)
- Outcome-aware re-ranking in `baseline_retrieval.py` directly applies bonuses (`+0.2` for `success`, `-0.2` for `regression`) based on retrieved cases.
- If test cases or identically templated cases leak into the retrieval pool, the evaluation directly uses the ground-truth outcome of the test distribution to pick the recommendation.

---

## 4. Exact Code Evidence for Each Risk

### Evidence 1: Explicit 50/50 Template Leakage in `split_strategy.py`
In [research/split_strategy.py#L110-L131](file:///C:/Users/swarsh/Desktop/autodba-research/research/split_strategy.py#L110-L131):
```python
def stratified_split(
    cases: List[str],
    template_groups: List[str],
    workload_labels: List[str],
) -> TrainTestSplit:
    template_to_indices = defaultdict(list)
    for i, case in enumerate(cases):
        template = case.get("incident_type", "")  # Uses incident_type as template placeholder
        template_to_indices[template].append(i)

    train_indices = []
    test_indices = []
    for template, idx_list in template_to_indices.items():
        n = len(idx_list)
        if n >= 2:
            # Distribute evenly between train and test
            for i in range(0, n, 2):
                train_indices.append(idx_list[i])
                if i + 1 < n:
                    test_indices.append(idx_list[i + 1])
```
*Proof:* Every group with $n \ge 2$ instances is systematically bisected into both `train_set` and `test_set`.

### Evidence 2: Retrieval Pool Contamination in `baseline_retrieval.py`
In [research/baseline_retrieval.py#L100-L109](file:///C:/Users/swarsh/Desktop/autodba-research/research/baseline_retrieval.py#L100-L109):
```python
class BaselineRetrievalMethods:
    def __init__(self, cases):
        self.cases = cases  # Full case dataset passed in

    def current_autodba_retrieval(self, query_case, limit=5, similarity_threshold=0.2):
        query_vector = self._get_embedding_vector(query_case)
        results = []
        for case in self.cases:
            if case.case_id == query_case.case_id: continue  # ONLY excludes exact self
            case_vector = self._get_embedding_vector(case)
            sim = cosine_similarity(query_vector, case_vector)
            if sim >= similarity_threshold:
                results.append(...)
```
*Proof:* The search space is `self.cases` (all cases across all splits). The only exclusion is identical `case_id`, permitting retrieval of all other test set members and template duplicates.

### Evidence 3: Non-Deterministic Python Built-in `hash()` in `baseline_retrieval.py`
In [research/baseline_retrieval.py#L152-L162](file:///C:/Users/swarsh/Desktop/autodba-research/research/baseline_retrieval.py#L152-L162):
```python
    def _get_embedding_vector(self, case):
        text = case.embedding_text
        if not text: return [0.0] * 128
        dims = 128
        vector = [0.0] * dims
        for token in re.findall(r'[a-zA-Z0-9_]+', text.lower()):
            hv = hash(token) & 0xFFFFFFFF  # Built-in hash() is randomized per process!
            vector[hv % dims] += 1.0 if (hv & 1) == 0 else -1.0
        mag = math.sqrt(sum(v*v for v in vector))
        return [v/mag for v in vector] if mag > 0 else vector
```
*Proof:* Python's `hash()` introduces non-deterministic representation drift between test runs due to `PYTHONHASHSEED`.

### Evidence 4: Runtime Import Crashes (`OptimizationCase` Missing)
In [research/case_schema.py#L183](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py#L183):
```python
def case_outcome(case: OptimizationCase) -> str:
    ...
```
In [research/evaluation_harness.py#L21](file:///C:/Users/swarsh/Desktop/autodba-research/research/evaluation_harness.py#L21):
```python
from .case_schema import OptimizationCase, QueryInfo, IncidentType, MeasurementQualityInfo
```
*Proof:* `OptimizationCase` is imported and used as a type annotation throughout `case_schema.py`, `baseline_retrieval.py`, and `evaluation_harness.py`, but is nowhere defined in `case_schema.py`. Executing `import research.evaluation_harness` immediately raises `ImportError: cannot import name 'OptimizationCase' from 'research.case_schema'`.

### Evidence 5: Mismatched Constructors & Mocked Execution in `evaluation_harness.py`
In [research/evaluation_harness.py#L45-L55](file:///C:/Users/swarsh/Desktop/autodba-research/research/evaluation_harness.py#L45-L55):
```python
        self.train_set = TrainTestSplit(
            cases=self.cases,
            template_groups=[...],
            workload_labels=[...],
            seed=42,
        )
```
*Proof:* `TrainTestSplit` in `split_strategy.py` accepts `(name, groups, seed, group_by, train_set, test_set)`. Passing `cases=...`, `template_groups=...`, `workload_labels=...` raises `TypeError: TrainTestSplit.__init__() got an unexpected keyword argument`.

---

## 5. What Currently Works

1. **Analytical Concepts & Schema Intent:**
   - Dataclass models in `case_schema.py` (`QueryInfo`, `PlanInfo`, `RecommendationAction`, `HypoPGValidation`, `MeasuredOutcome`, `MeasurementQualityInfo`) capture the necessary metadata for optimization incidents.
2. **Phase 1 & Phase 2 Application Foundations:**
   - `CandidateEvaluation` in `app/schemas/optimization.py` provides deterministic candidate generation and safety evaluation.
   - `OptimizationMemoryModel`, `CaseProvenance`, and `OutcomeVerificationState` provide verified provenance tagging in the backend.

---

## 6. What is Placeholder / Broken

1. `OptimizationCase` dataclass definition is missing from `case_schema.py`.
2. `TrainTestSplit` class definition in `split_strategy.py` does not match the constructor calls in `evaluation_harness.py`.
3. `stratified_split()` implements round-robin cross-split template leaking.
4. `BaselineRetrievalMethods._get_embedding_vector()` uses randomized `hash()`.
5. `BaselineRetrievalMethods` allows querying against the test set.
6. `EvaluationHarness.compute_metrics()` is an unexecuted stub (`# TODO`).
7. `EvaluationFramework` and `ResearchHarness` rely on hardcoded heuristic return values.

---

## 7. Required Information for a Scientifically Valid Split

To guarantee zero template and instance leakage, every historical optimization case must provide:

1. **Canonical Template Fingerprint (`template_hash`):**
   - Normalized SQL where all numeric, string, list, and boolean literals, parameter markers (`$1`, `?`), whitespace, and casing are normalized to a canonical placeholder query.
2. **Workload / Relation Domain (`relation_group`):**
   - The primary tables/relations involved in the query (e.g. `orders`, `order_items`, `customers`).
3. **Incident Classification (`incident_type`):**
   - The primary bottleneck category (`missing_index`, `filtered_seq_scan`, etc.).
4. **Group Key Formulation:**
   $$\text{GroupKey} = \text{MD5}(\text{incident\_type} \parallel \text{sorted\_tables} \parallel \text{canonical\_template})$$
5. **Group-Level Partitioning Rule:**
   - **All** cases sharing the same $\text{GroupKey}$ must be assigned exclusively to `TRAIN` or exclusively to `TEST`. Under no circumstances may a $\text{GroupKey}$ be split across partitions.

---

## 8. Proposed Leakage-Safe Split Design

```
Raw Cases Pool (N cases)
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Grouping Stage                                         │
│ Compute Canonical Template & GroupKey for each case    │
│ Group cases: Dict[GroupKey, List[OptimizationCase]]   │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Group-Level Disjoint Partitioning                     │
│ Deterministic shuffle by GroupKey using random seed    │
│                                                        │
│ Train Groups (e.g. 70% of Groups)                     │
│ Test Groups  (e.g. 30% of Groups)                     │
└────────────────────────────────────────────────────────┘
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ TRAIN / HISTORY POOL         │  │ TEST / EVALUATION POOL       │
│ (All cases of Train Groups)  │  │ (All cases of Test Groups)   │
└──────────────────────────────┘  └──────────────────────────────┘
```

### Mathematical Invariants:
1. $\text{Templates}(\text{Train}) \cap \text{Templates}(\text{Test}) = \emptyset$
2. $\text{Cases}(\text{Train}) \cap \text{Cases}(\text{Test}) = \emptyset$
3. $\text{RetrievalPool}(\text{for any test evaluation}) \equiv \text{Cases}(\text{Train})$

---

## 9. Proposed Evaluation Data Flow

```
                      ┌────────────────────────────────────────┐
                      │ Target Test Case (Unseen Query Q_test) │
                      └────────────────────────────────────────┘
                                           │
                                           │ 1. Extract SQL & Incident
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Leakage-Safe Retrieval Stage                                                     │
│ Query: Q_test (raw query text or deterministic SHA-256 embedding)                │
│ Index: TRAIN / HISTORY POOL ONLY (Zero test cases present in index)              │
│ Filter: Optional verified_only=True (Phase 2 provenance filter)                  │
│ Output: Top-K Similar Historical Cases (from Train Pool only)                    │
└──────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ 2. Enriched Context
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Deterministic Candidate Evaluation Stage (Phase 1 Pipeline)                      │
│ Generate: Candidate index recommendations for Q_test                             │
│ Validate: HypoPG counterfactual cost improvement                                 │
│ Safety: SafetyAssessor validation                                                │
│ Output: Validated Candidate Evaluation Pool                                      │
└──────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           │ 3. Ranking Policy Evaluation
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Ranking & Outcome Comparison                                                     │
│ Baseline: Planner-only cost reduction rank                                       │
│ Policy: Outcome-aware historical rank (Phase 4)                                  │
│ Ground Truth: Compare selected candidate against actual measured outcome         │
│ Metric: Success Rate, Regression Rate, Cost Error, Recall@K                      │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Minimal Implementation Plan for Phase 3

1. **Fix Canonical Case Schema (`research/case_schema.py`):**
   - Add the missing `OptimizationCase` dataclass definition with complete type annotations.
   - Implement robust SQL normalization (`canonical_sql_template`) that replaces string literals, numeric literals, and in-lists.
   - Align provenance with `app.schemas.optimization.CaseProvenance`.
2. **Implement Grouped Leakage-Safe Split (`research/split_strategy.py`):**
   - Replace flawed `stratified_split()` with `grouped_template_split(cases, group_by, test_ratio, seed)`.
   - Add explicit invariant verification function `verify_split_leakage(split, cases)` that asserts $\text{Templates}(\text{Train}) \cap \text{Templates}(\text{Test}) = \emptyset$.
3. **Align Research Embeddings & Retrieval (`research/baseline_retrieval.py`):**
   - Replace `hash()` with deterministic SHA-256 token hashing matching application `EmbeddingService`.
   - Update `BaselineRetrievalMethods` to accept separate `history_corpus` (train set) and `query_case` (test set).
4. **Repair Evaluation Harness Orchestration (`research/evaluation_harness.py`):**
   - Fix constructor and method call signatures.
   - Implement real metric calculations (Recall@K, Mean Reciprocal Rank, Regression Avoidance Rate, Empirical Runtime Delta).

---

## 11. Explicit List of Things That Should NOT Be Changed Yet

- **DO NOT** modify backend application code (`autodba-main/backend/app/`).
- **DO NOT** modify Phase 1 candidate evaluation logic (`_evaluate_candidates`).
- **DO NOT** modify Phase 2 provenance models or database schemas (`03-intelligence.sql`, `04-*.sql`).
- **DO NOT** implement Phase 4 ranking policies or heuristic scoring formulas.
- **DO NOT** modify production database monitor, HypoPG validator, or closed-loop services.
- **DO NOT** run live database benchmarks or full test suites.
- **DO NOT** commit until Phase 3 foundation design is reviewed and approved.
