# Phase 3 Split Design: Leakage-Safe Query Pattern & Grouping Foundation

**Location:** `research/PHASE3_SPLIT_DESIGN.md`  
**Workspace:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Date:** 2026-10-01  

---

## 1. Existing Query Pattern Identification Fields

Inspection of the research schema ([case_schema.py](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py)), sample cases ([data/sample_cases.json](file:///C:/Users/swarsh/Desktop/autodba-research/research/data/sample_cases.json)), and backend application models ([models.py](file:///C:/Users/swarsh/Desktop/autodba-research/autodba-main/backend/app/db/models.py)) reveals the following candidate fields:

| Field | Source Location | Current Representation | Suitability for Pattern Grouping |
| :--- | :--- | :--- | :--- |
| `query_text` / `query` | `OptimizationMemoryModel`, `sample_cases.json` | Raw SQL string (e.g. `SELECT * FROM orders WHERE customer_id = 42`) | **Unsuitable alone:** Retains literals; exact matching misses identical patterns. |
| `query_fingerprint` | `OptimizationMemoryModel`, `MemoryService` | SHA-256 hash of lowercase whitespace-collapsed raw SQL | **Unsuitable for template grouping:** Preserves literals; `customer_id = 42` and `customer_id = 99` produce distinct hashes. |
| `QueryInfo.template` | `research/case_schema.py` | String from regex `sql_template()` | **Partially suitable, but flawed:** Does not normalize string literals (`'pending'`), in-lists, or positional parameters (`$1`). |
| `QueryInfo.normalized_sql` | `research/case_schema.py` | String from `normalize_sql()` | **Incomplete:** Only replaces digits with `?`, leaving string literals intact. |
| `incident_type` | `OptimizationMemoryModel`, `sample_cases.json` | Enum / String (`missing_index`, `expensive_sort`, etc.) | **Contextual attribute, not query pattern:** Different queries can have the same incident; same query could yield different findings. |
| `recommendation.table` | `sample_cases.json`, `diagnosis` | Target table string (e.g. `orders`) | **Coarse domain scope:** Groups all queries hitting `orders`, but lacks query structure granularity. |

---

## 2. What `query_fingerprint` Actually Represents

Tracing `query_fingerprint` in [`MemoryService._fingerprint()`](file:///C:/Users/swarsh/Desktop/autodba-research/autodba-main/backend/app/services/memory_service.py#L279):
```python
@staticmethod
def _fingerprint(query_text: str) -> str:
    normalized = " ".join(query_text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

### Finding:
- `query_fingerprint` represents **(a) Exact SQL text identity (modulo whitespace and casing)**.
- It is **not** a query template identifier.
- It is **not** an AST structure fingerprint.
- It is **not** a workload identity.

### Consequence:
Two executions of the identical query pattern with differing literals:
- $Q_1$: `SELECT * FROM orders WHERE customer_id = 42` $\to$ `fingerprint = 3a1f...`
- $Q_2$: `SELECT * FROM orders WHERE customer_id = 99` $\to$ `fingerprint = 8c9b...`

If `query_fingerprint` were used as the split grouping key, $Q_1$ would be placed in `TRAIN` and $Q_2$ in `TEST`. The test set would evaluate a query template the model has already memorized in training. **`query_fingerprint` cannot be reused as the leakage-safe template grouping key.**

---

## 3. Query Pattern Taxonomy on `sample_cases.json`

Analyzing the queries in [research/data/sample_cases.json](file:///C:/Users/swarsh/Desktop/autodba-research/research/data/sample_cases.json):

```json
seed-001: SELECT * FROM orders WHERE customer_id = 42
seed-002: SELECT * FROM orders ORDER BY order_date DESC
sim-001:  SELECT * FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.id = 99
sim-002:  SELECT * FROM order_items WHERE product_id = 17
```

### Categorization Criteria:
1. **Identical Query Template (Must be in same partition):**
   - `SELECT * FROM orders WHERE customer_id = 42`
   - `SELECT * FROM orders WHERE customer_id = 99`
   - `select * from orders where customer_id = ?`
   - *Rule:* Differing only in numeric/string literals, parameter markers (`$1`, `?`), or whitespace/casing.
2. **Different Query Template on Same Table (Fine-grained separation):**
   - $T_A$: `SELECT * FROM orders WHERE customer_id = ?` (single equality filter)
   - $T_B$: `SELECT * FROM orders WHERE customer_id = ? AND status = ?` (composite filter)
   - $T_C$: `SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC` (filter + sort)
   - *Rule:* Predicate set, join topology, or ordering clauses differ.
3. **Materially Different Query Structure:**
   - Single-table filter vs. 2-table Join (`orders JOIN customers`) vs. Table Scan/Sort vs. Aggregate.

---

## 4. Evaluation of Proposed Grouping Key

### Evaluated Key:
$$\text{GroupKey} = \text{incident\_type} + \text{sorted\_tables} + \text{canonical\_template}$$

### Analysis:
1. **What Leakage it Prevents:**
   - Prevents identical canonical SQL templates with different literals from splitting across train and test.
2. **What Leakage it Permits (The `incident_type` Hazard):**
   - **Hazard:** If `incident_type` is included in the grouping key, the **exact same query template** could produce `incident_type="missing_index"` under one execution and `incident_type="filtered_seq_scan"` under another (e.g. before/after planner state changes).
   - If so, $(\text{missing\_index}, \text{orders}, T)$ would be assigned to `TRAIN`, while $(\text{filtered\_seq_scan}, \text{orders}, T)$ would be assigned to `TEST`.
   - **Result:** Direct template leakage across splits.
   - **Conclusion on `incident_type`:** `incident_type` **must NOT** be part of the primary grouping key. Query structure is the invariant property of the query pattern.
3. **Are Sorted Tables Sufficient?**
   - Sorted tables identify the relation domain (e.g. `['customers', 'orders']`).
   - Grouping purely by `sorted_tables` would coarsen the split so that *all* queries touching `orders` are placed in Train or Test, leaving zero evaluation queries for `orders`.
   - Canonical template structure must be the primary grouping key.

### Refined Grouping Key:
$$\text{CanonicalTemplate} = \text{canonicalize\_sql}(\text{query\_text})$$
$$\text{TemplateGroupKey} = \text{SHA256}(\text{CanonicalTemplate})$$

---

## 5. Feasibility of Pure-Python SQL Normalization

Can robust normalization be achieved without introducing heavy third-party SQL parser dependencies (e.g. `sqlglot`, `pglast`)?

### Assessment:
**Yes.** For PostgreSQL read-only query workloads within AutoDBA's evaluation domain, a deterministic regex-based tokenizer and normalizer in standard library Python (`re`, `hashlib`) is completely sufficient, zero-dependency, and deterministic.

### Normalization Pipeline (`canonicalize_sql`):
1. Strip leading/trailing whitespace and comments (`-- ...`, `/* ... */`).
2. Collapse whitespace sequences (`\s+` $\to$ `' '`).
3. Lowercase SQL keywords and unquoted identifiers.
4. Replace numeric literals (`\b\d+(\.\d+)?\b` $\to$ `?`).
5. Replace single-quoted string literals (`'([^']|'')*'` $\to$ `?`).
6. Replace parameterized variables (`\$\d+` $\to$ `?`).
7. Normalize in-lists: `in\s*\(\s*\?(?:\s*,\s*\?)*\s*\)` $\to$ `in (?)`.
8. Normalize comparison operators (e.g. `< >` $\to$ `<>`).
9. Normalize spacing around punctuation (`,`, `(`, `)`, `=`, `<`, `>`).

### Example Transformations:
- `SELECT * FROM orders WHERE customer_id = 42;` $\to$ `select * from orders where customer_id = ?`
- `SELECT * FROM Orders WHERE customer_id = 99 AND status = 'pending';` $\to$ `select * from orders where customer_id = ? and status = ?`
- `SELECT * FROM order_items WHERE product_id IN (1, 2, 3);` $\to$ `select * from order_items where product_id in (?)`

---

## 6. Minimum Defensible Grouping Rule

1. **Mapping:** Every case $c \in \mathcal{C}$ maps to a canonical template $T(c) = \text{canonicalize\_sql}(c.\text{query\_text})$.
2. **Partitioning:**
   - Form groups $\mathcal{G}_T = \{ c \in \mathcal{C} \mid T(c) = T \}$.
   - Partition the distinct template keys $\{ T \}$ into disjoint subsets $\mathcal{T}_{\text{train}}$ and $\mathcal{T}_{\text{test}}$ using a deterministic pseudo-random shuffle parameterized by `seed`.
   - $\mathcal{C}_{\text{train}} = \bigcup_{T \in \mathcal{T}_{\text{train}}} \mathcal{G}_T$
   - $\mathcal{C}_{\text{test}} = \bigcup_{T \in \mathcal{T}_{\text{test}}} \mathcal{G}_T$

---

## 7. Exact Leakage Invariants to Formally Assert

In `split_strategy.py`, the function `verify_split_leakage(split, cases)` must assert the following 7 mathematical invariants:

1. **Disjoint Template Sets (Zero Template Leakage):**
   $$\{ T(c) \mid c \in \text{Train} \} \cap \{ T(c) \mid c \in \text{Test} \} = \emptyset$$
2. **Disjoint Case IDs (Zero Instance Leakage):**
   $$\{ c.\text{case\_id} \mid c \in \text{Train} \} \cap \{ c.\text{case\_id} \mid c \in \text{Test} \} = \emptyset$$
3. **Partition Completeness:**
   $$\text{Train} \cup \text{Test} = \mathcal{C} \quad \land \quad \text{Train} \cap \text{Test} = \emptyset$$
4. **Retrieval Corpus Exclusivity:**
   $$\text{RetrievalCorpus}(\text{for evaluation}) \equiv \text{TrainCases}$$
5. **Zero Target Contamination:**
   $$\forall c_{\text{test}} \in \text{TestCases}, \quad c_{\text{test}} \notin \text{RetrievalCorpus}$$
6. **Zero Target Template in Retrieval Pool:**
   $$\forall c_{\text{test}} \in \text{TestCases}, \quad T(c_{\text{test}}) \notin \{ T(c_{\text{train}}) \mid c_{\text{train}} \in \text{RetrievalCorpus} \}$$
7. **Deterministic Reproducibility:**
   $$\text{Split}(\mathcal{C}, \text{seed}=S) \equiv \text{Split}(\mathcal{C}, \text{seed}=S) \quad \forall \text{ runs}$$

---

## 8. Query Fingerprint Reuse Decision

- **Decision:** **Do NOT reuse application `query_fingerprint` for template grouping.**
- **Rationale:** `query_fingerprint` serves a separate application-layer purpose (exact query text cache key). Conflating exact query hashing with template normalization would corrupt both the memory store and the evaluation split.
- **Action:** Introduce a dedicated `canonical_template` (string) and `template_hash` (SHA-256 string) in `research/case_schema.py`.

---

## 9. Minimal Implementation Plan

### 1. `research/case_schema.py`:
- Add `canonicalize_sql(sql: str) -> str` and `compute_template_hash(sql: str) -> str`.
- Define the complete `OptimizationCase` dataclass including `case_id`, `query: QueryInfo`, `plan: PlanInfo`, `recommendation: RecommendationAction`, `hypopg_validation: HypoPGValidation`, `measured_outcome: MeasuredOutcome`, `provenance: CaseProvenance`, `is_verified: bool`, `verification_state: OutcomeVerificationState`.
- Add `from_dict()` / `to_dict()` loaders to parse `sample_cases.json` and backend `OptimizationMemory` records.

### 2. `research/split_strategy.py`:
- Implement `GroupedTemplateSplitter` with `split_cases(cases, test_ratio=0.3, seed=42)`.
- Implement `verify_split_leakage(train_set, test_set)` to enforce all 7 invariants.

### 3. `research/baseline_retrieval.py`:
- Replace non-deterministic `hash()` in `_get_embedding_vector()` with deterministic SHA-256 token hashing matching application `EmbeddingService`.
- Structure `BaselineRetrievalMethods` to accept `train_corpus` as the fixed search space, taking `test_query` as the query input.

### 4. `research/evaluation_harness.py`:
- Update `EvaluationHarness` to orchestrate `GroupedTemplateSplitter` and pass `train_cases` to `BaselineRetrievalMethods`.
- Implement real metric calculations (Recall@K, MRR, Success/Regression Counts).

---

## Summary of Design Answers

- **A. Definition of "Unseen Query Pattern":** A query structure whose canonical parameterized SQL template (stripping all literals, in-lists, and formatting) does not exist anywhere within the historical training/retrieval memory.
- **B. Exact Grouping Key:** $\text{SHA256}(\text{canonicalize\_sql}(\text{query\_text}))$.
- **C. Exact Leakage Invariants:** 7 mathematical invariants defined in Section 7 above.
- **D. Is existing `query_fingerprint` sufficient?** No; it hashes literal values and must remain separate.
- **E. Files that will eventually need modification:** `research/case_schema.py`, `research/split_strategy.py`, `research/baseline_retrieval.py`, `research/evaluation_harness.py`.
- **F. Unresolved Ambiguity:** None. Pure standard-library normalization is fully feasible and unambiguous.
