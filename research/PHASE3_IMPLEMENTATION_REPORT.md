# Phase 3 Implementation Report: Leakage-Safe Evaluation Foundation

**Location:** `research/PHASE3_IMPLEMENTATION_REPORT.md`  
**Workspace:** `C:\Users\swarsh\Desktop\autodba-research`  
**Branch:** `research/outcome-aware-ranking`  
**Date:** 2026-10-01  

---

## 1. Files Changed

All implementation changes are confined strictly to the research scaffolding in `C:\Users\swarsh\Desktop\autodba-research`:

1. [**`research/case_schema.py`**](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py)
   - Defined the canonical [`OptimizationCase`](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py) dataclass and loaders (`from_dict`, `to_dict`).
   - Implemented standard-library SQL canonicalizer [`canonicalize_sql`](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py) and [`compute_template_hash`](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py).
   - Aligned provenance and verification fields with Phase 2 models (`CaseProvenance`, `is_verified`, `verification_state`).
2. [**`research/split_strategy.py`**](file:///C:/Users/swarsh/Desktop/autodba-research/research/split_strategy.py)
   - Replaced round-robin/template-leaking code with [`grouped_template_split`](file:///C:/Users/swarsh/Desktop/autodba-research/research/split_strategy.py).
   - Implemented strict group-level partitioning by `template_hash`.
   - Added [`verify_split_leakage`](file:///C:/Users/swarsh/Desktop/autodba-research/research/split_strategy.py) asserting zero template overlap, zero ID overlap, and partition completeness.
3. [**`research/baseline_retrieval.py`**](file:///C:/Users/swarsh/Desktop/autodba-research/research/baseline_retrieval.py)
   - Constructed [`BaselineRetrievalMethods`](file:///C:/Users/swarsh/Desktop/autodba-research/research/baseline_retrieval.py) strictly from the `TRAIN` case corpus.
   - Enforced strict exclusion of test cases and target templates from candidate retrieval.
   - Replaced Python's randomized built-in `hash()` with deterministic SHA-256 token hashing.
4. [**`research/evaluation_harness.py`**](file:///C:/Users/swarsh/Desktop/autodba-research/research/evaluation_harness.py)
   - Repaired interface/type mismatches and established the leakage-safe evaluation pipeline.
   - Formally separated historical candidate retrieval from test evaluation without fabricating outcome numbers.

---

## 2. Canonicalization Definition

The canonicalization function [`canonicalize_sql(query_text)`](file:///C:/Users/swarsh/Desktop/autodba-research/research/case_schema.py) deterministically maps a raw SQL query string to its canonical parameterized structural form:

1. **Comments Stripping:** Removes single-line (`--`) and multi-line (`/* ... */`) SQL comments.
2. **Whitespace & Casing:** Collapses whitespace sequences (`\s+` $\to$ `' '`) and converts to lowercase.
3. **String Literal Parameterization:** Replaces `'...'` literals (including escaped quotes) with `?`.
4. **Numeric Literal Parameterization:** Replaces integer and floating-point literals with `?`.
5. **Parameter Marker Parameterization:** Replaces `$1`, `$2`, etc., with `?`.
6. **Boolean Parameterization:** Replaces `true`/`false` literal values with `?`.
7. **IN-List Normalization:** Collapses variable-length in-lists (`IN (?, ?, ?)`) to `IN (?)`.
8. **Punctuation & Operators:** Standardizes spacing around commas, parentheses, and comparison operators (`=`, `<>`, `<=`, `>=`, `!=`).
9. **Trailing Semicolons:** Strips trailing delimiters.

The template group identifier is defined as:
$$\text{template\_hash} = \text{SHA256}(\text{canonicalize\_sql}(\text{query\_text}))$$

---

## 3. Canonicalization Scope and Limitations

- **Scope:** We define a deterministic canonicalization procedure for the SQL forms represented in the evaluation corpus.
- **Explicit Limitations:**
  - This is **not** a universal PostgreSQL parser and does not construct a full relational AST.
  - Queries with semantically equivalent but syntactically distinct AST structures (e.g. `WHERE a = ? AND b = ?` vs. `WHERE b = ? AND a = ?` or explicit `JOIN` vs. comma-join syntax) will produce distinct template hashes. This preserves conservative safety: it may separate slightly reordered queries into different groups, but will **never** falsely merge structurally distinct queries into the same group.

---

## 4. Grouping Rule

1. Every case $c$ is assigned a template group key $\text{GroupKey}(c) = c.\text{template\_hash}$.
2. Cases are grouped by $\text{GroupKey}$.
3. Distinct template groups are deterministically shuffled using a pseudo-random number generator parameterized by `seed`.
4. Partitioning allocates entire template groups strictly to either `TRAIN` or `TEST`.
5. `incident_type` is **not** used as a primary grouping signal, preventing identical query structures from crossing split boundaries under different incident classifications.

---

## 5. Leakage Invariants Formally Enforced

The split implementation explicitly checks and validates:

1. **Zero Template Overlap:**
   $$\text{TrainTemplates} \cap \text{TestTemplates} = \emptyset$$
2. **Zero Case ID Overlap:**
   $$\text{TrainCaseIDs} \cap \text{TestCaseIDs} = \emptyset$$
3. **Partition Completeness:**
   $$\text{TrainCases} \cup \text{TestCases} = \mathcal{C} \quad \land \quad \text{TrainCases} \cap \text{TestCases} = \emptyset$$
4. **Target Template Exclusion:**
   $$\forall c_{\text{test}} \in \text{TestCases}, \quad c_{\text{test}}.\text{template\_hash} \notin \text{TrainTemplates}$$
5. **Deterministic Reproducibility:**
   $$\text{Split}(\mathcal{C}, \text{seed}=S) \equiv \text{Split}(\mathcal{C}, \text{seed}=S) \quad \forall \text{ runs}$$

---

## 6. Retrieval Isolation Architecture

```
All Historical Cases (N)
         │
         ▼
┌─────────────────────────────────┐
│ Grouped Template Split          │
└─────────────────────────────────┘
         │
         ├──────────────────────────────┐
         ▼                              ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ TRAIN PARTITION              │ │ TEST PARTITION               │
│ (Template Groups A, B, C)    │ │ (Template Groups D, E)       │
└──────────────────────────────┘ └──────────────────────────────┘
         │                              │
         ▼                              │
┌──────────────────────────────┐        │
│ BaselineRetrievalMethods     │        │
│ (Index built on Train ONLY)  │        │
└──────────────────────────────┘        │
         ▲                              │
         │ (Query: Q_test)              │
         └──────────────────────────────┘
```

- When evaluating any test case, the retrieval index contains **only** `TRAIN` partition cases.
- Test cases never enter the retrieval search space.
- A test case cannot retrieve itself, another test case, or any historical case sharing its canonical template.

---

## 7. What Was Fixed

1. `OptimizationCase` class definition implemented with full typing and dictionary loaders.
2. Replaced 50/50 round-robin template leaking with strict disjoint template group splitting.
3. Fixed retrieval candidate pool to index only training history.
4. Replaced non-deterministic `hash()` with SHA-256 token hashing.
5. Fixed `EvaluationHarness` type errors, argument mismatches, and broken method calls.

---

## 8. What Remains Unimplemented (Phase 4 Scope)

1. **Outcome-Aware Candidate Ranking Policies:** No scoring formula or candidate re-ranking algorithm has been applied to AutoDBA recommendations.
2. **Evaluation Metrics Execution:** Recall@K, empirical success rate, and runtime improvement deltas will be calculated when benchmark evaluation queries are executed.

---

## 9. Explicit List of Claims NOT Yet Supported

- We do **NOT** claim that outcome-aware ranking outperforms the planner-only baseline.
- We do **NOT** claim that retrieval quality has improved.
- We do **NOT** claim that the regex canonicalizer is a universal SQL parser.
- We claim **ONLY** that the evaluation data boundary is now structurally leakage-safe.
