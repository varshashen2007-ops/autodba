# AutoDBA — Research Upgrade Transfer Analysis

**Date:** 2026-10-03  
**Status:** READ-ONLY ANALYSIS — NO FILES MODIFIED

---

## 1. Repository Map

| Label | Path | Role |
|:---|:---|:---|
| **A — Original Reference** | `C:\Users\swarsh\Desktop\autodba-main` | Permanent reference. Contains the original application baseline (`autodba-main/`) and the pre-existing research contribution (`research/`). **Never modify.** |
| **B — Research Working Copy** | `C:\Users\swarsh\Desktop\autodba-research` | Our development repo. Git-tracked (HEAD `2fec570`). Contains the application with all research upgrades applied, plus full Phase 1–8 research pipeline. |
| **C — Teammate Repository** | `C:\Users\swarsh\Desktop\autodba-transfer` | Fresh clone of `https://github.com/varshashen2007-ops/autodba`. HEAD `8560855`. This is the destination for our upgrades. |

### A: Original Reference — Structure

```
autodba-main/
  autodba-main/       ← original application (the TRUE baseline for application changes)
    backend/
    frontend/
    postgres/
  research/           ← pre-existing research contribution (NOT new Phase 1–8 work)
    ablation_study.py
    baseline_retrieval.py
    case_schema.py
    evaluation_framework.py
    evaluation_harness.py
    experiment_manifest.json / .md
    harness.py
    metrics.py
    requirements.txt
    split_strategy.py
    data/sample_cases.json
    README.md
```

### B: Our Research Working Copy — Structure

```
autodba-research/
  .git/               ← research git history (9 commits)
  autodba-main/       ← application with research upgrades applied
    backend/
    frontend/ (unchanged)
    postgres/init/ (03-intelligence.sql upgraded, 04-*.sql added)
  research/           ← upgraded research libraries + Phase 1–8 artifacts (36 untracked files)
```

### C: Teammate Repository — Structure

```
autodba-transfer/
  .git/               ← teammate git history (3 commits)
  backend/            ← Note: no autodba-main/ subdirectory — flat structure
  frontend/
  postgres/
  (no research/ directory)
```

> **Critical structural difference:** The teammate repository has a **flat structure** at root
> (`backend/`, `frontend/`, `postgres/`), whereas our repo has these under `autodba-main/`.
> When transferring, all paths must be adjusted accordingly.

---

## 2. Original Baseline

### 2a. Original Application Code

Located at `A\autodba-main\autodba-main\`. This is the true application baseline. It includes:

- `backend/app/services/intelligence_service.py` — base IntelligenceService **without** `_evaluate_candidates`
- `backend/app/schemas/optimization.py` — **no** `CandidateEvaluation`, `CaseProvenance`, `OutcomeVerificationState`
- `backend/app/db/models.py` — `OptimizationMemoryModel` **without** `provenance`, `is_verified`, `verification_state` columns
- `backend/app/services/memory_service.py` — **no** `verified_only` / `provenance` filtering
- `backend/app/services/rag_service.py` — **no** `verified_only` / `provenance` params
- `backend/app/api/v1/intelligence_memory.py` — exists but **no** provenance-aware routes
- `backend/app/scripts/seed_intelligence.py` — seeds without provenance fields
- `postgres/init/03-intelligence.sql` — schema **without** `provenance`, `is_verified`, `verification_state` columns
- `postgres/init/04-*.sql` — **does not exist** in original

### 2b. Pre-Existing Research Contribution

Located at `A\research\`. These files existed **before** our Phase 1–8 work and must NOT be
reported as new upgrades:

| File | Original Lines |
|:---|:---:|
| `research/ablation_study.py` | 151 |
| `research/baseline_retrieval.py` | 178 |
| `research/case_schema.py` | 191 |
| `research/evaluation_framework.py` | 128 |
| `research/evaluation_harness.py` | 130 |
| `research/experiment_manifest.json` | original |
| `research/experiment_manifest.md` | original |
| `research/harness.py` | 102 |
| `research/metrics.py` | 52 |
| `research/requirements.txt` | original |
| `research/split_strategy.py` | 132 |
| `research/data/sample_cases.json` | 147 |
| `research/data/README.md` | original |
| `research/README.md` | 141 |

---

## 3. Our Actual Research Upgrades

These are the changes introduced during our Phase 1–8 work, determined by diffing commits
`4b92f1c` → `2fec570` in the research working copy, then excluding pre-existing research files.

### A. APPLICATION CODE CHANGES (git-tracked, commits 012a285 + 711d1da)

| # | Upgrade | Original State | Our New State | File |
|:---:|:---|:---|:---|:---|
| A1 | Deterministic multi-candidate evaluation | `diagnose()` returns single recommendation | `diagnose()` calls `_evaluate_candidates()`, returns `CandidateEvaluation[]` list with HypoPG+safety per candidate | `intelligence_service.py` |
| A2 | `CandidateEvaluation` schema | Does not exist | New Pydantic model: `candidate_id`, `recommendation`, `validation`, `safety_assessment`, `is_baseline` | `schemas/optimization.py` |
| A3 | `CaseProvenance` enum | Does not exist | New enum: `measured`, `seeded`, `synthetic`, `unverified` | `schemas/optimization.py` |
| A4 | `OutcomeVerificationState` enum | Does not exist | New enum: `verified_measured`, `unverified`, `synthetic` | `schemas/optimization.py` |
| A5 | Provenance fields on `OptimizationMemory` schema | No provenance fields | Added `provenance`, `is_verified`, `verification_state` | `schemas/optimization.py` |
| A6 | Provenance fields on `SimilarCase` schema | No provenance fields | Added `provenance`, `is_verified`, `verification_state` | `schemas/optimization.py` |
| A7 | Provenance columns on ORM model | No provenance columns | Added `provenance`, `is_verified`, `verification_state` mapped columns | `db/models.py` |
| A8 | Provenance-aware memory retrieval | No filtering by provenance or verification | `memory_service.search()` supports `verified_only` and `provenance` filters | `services/memory_service.py` |
| A9 | RAG provenance filtering | No provenance params | `rag_service.retrieve()` passes `verified_only` and `provenance` to memory | `services/rag_service.py` |
| A10 | `verified_only` in `RAGContext` response | Not present | `RAGContext.verified_only` field added | `schemas/optimization.py` |
| A11 | `MemorySearchRequest` provenance filter | Not present | `verified_only`, `provenance` added to search request schema | `schemas/optimization.py` |
| A12 | Seed data with provenance | Seeds have no provenance fields | Seed sets `provenance=measured`, `is_verified=True`, `verification_state=verified_measured` | `scripts/seed_intelligence.py` |
| A13 | `DiagnosisResult.candidate_evaluations` field | Not present | `candidate_evaluations: list[CandidateEvaluation]` added | `schemas/optimization.py` |

### B. DATABASE / SCHEMA CHANGES

| # | Upgrade | Original State | Our New State | File |
|:---|:---|:---|:---|:---|
| B1 | Provenance columns in DDL | `optimization_memories` has no provenance cols | Added `provenance`, `is_verified`, `verification_state` with defaults | `postgres/init/03-intelligence.sql` |
| B2 | Provenance indexes | No provenance indexes | Added `idx_optimization_memories_provenance`, `idx_optimization_memories_is_verified` | `postgres/init/03-intelligence.sql` |
| B3 | Additive migration | Does not exist | New file: idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` for provenance fields | `postgres/init/04-intelligence-provenance-migration.sql` |

### C. RESEARCH LIBRARY UPGRADES (git-tracked, commits ca20fda, bd64709, 9823441, f9f1152, 2fec570)

These files existed in the original but were substantially upgraded:

| File | Original Lines | Upgraded Lines | Nature of Upgrade |
|:---|:---:|:---:|:---|
| `research/case_schema.py` | 191 | 436 | Added `canonicalize_sql`, `compute_template_hash`, `OptimizationCase` full model, `HypoPGValidation`, `MeasuredOutcome`, provenance fields |
| `research/evaluation_harness.py` | 130 | 258 | Added `EvaluationHarness` class, `SelectionPolicy` enum, leakage-verified evaluation loop |
| `research/baseline_retrieval.py` | 178 | 301+ | Added `BaselineRetrievalMethods`, `compute_token_hash_similarity`, multi-strategy retrieval |
| `research/split_strategy.py` | 132 | 260 | Added `grouped_template_split`, `verify_split_leakage`, template-hash-based partitioning |

Entirely new research files (not in original):

| File | Classification |
|:---|:---|
| `research/candidate_selector.py` | NEW — Policy A/B/C, `CandidateSelector`, `canonical_candidate_key` |
| `research/measured_case_runner.py` | NEW — `MeasuredCaseRunner`, `ResearchSafetyError`, W=2/N=10 protocol |

### D. PHASE 1–8 DOCUMENTATION / ARTIFACTS (all untracked, not in original)

Phase 3–8 markdown reports, JSON manifests, execution scripts, and data files. Full list
in `HANDOFF/PIPELINE_FREEZE.md`.

---

## 4. Teammate Repository State

**HEAD:** `8560855` — `fix: align frontend RAG fields and Groq model label`  
**Structure:** Flat root (`backend/`, `frontend/`, `postgres/`) — no `autodba-main/` wrapper.  
**Branches:** `main`, `phase-4-1-rag-llm`  
**Working tree:** Clean (no uncommitted changes)

### What the teammate has implemented:

| Component | Present? | Notes |
|:---|:---:|:---|
| `backend/` full FastAPI app | ✅ | Complete — all services present |
| `frontend/` React/Vite app | ✅ | Complete with multiple views |
| `postgres/init/03-intelligence.sql` | ✅ | Present but **without** provenance columns |
| `postgres/init/04-*.sql` | ❌ | Does not exist |
| `backend/app/services/intelligence_service.py` | ✅ | Present — **no** `_evaluate_candidates` |
| `backend/app/schemas/optimization.py` | ✅ | Present — **no** `CandidateEvaluation`, `CaseProvenance`, `OutcomeVerificationState` |
| `backend/app/db/models.py` | ✅ | Present — **no** provenance columns on ORM model |
| `backend/app/services/memory_service.py` | ✅ | Present — **no** `verified_only`/`provenance` filtering |
| `backend/app/services/rag_service.py` | ✅ | Present — **no** `verified_only`/`provenance` params |
| `backend/app/api/v1/intelligence_memory.py` | ✅ | Present — same basic structure, no provenance routes |
| `backend/app/scripts/seed_intelligence.py` | ✅ | Present — seeds **without** provenance fields |
| `research/` directory | ❌ | **Does not exist** in teammate repo |
| `research/candidate_selector.py` | ❌ | Missing |
| `research/case_schema.py` (upgraded) | ❌ | Missing upgraded version |
| `research/measured_case_runner.py` | ❌ | Missing |
| Phase 6–8 artifacts | ❌ | None present |

The teammate's `intelligence_service.py` (171 lines) is at **Phase 4.1** — it has the full
diagnosis pipeline with LLM integration but **no candidate evaluation logic**.

The teammate has additional frontend work beyond our baseline (RAG fields alignment,
Groq model label fix in commit `8560855`) that we did not add.

---

## 5. Three-Way Integration Analysis

> **Path note:** In our repo files live under `autodba-main/backend/...`; in the teammate
> repo they live directly at `backend/...`. All path comparisons below use the logical path.

| File/Component | Original (A) | Our Upgrade (B) | Team Current (C) | Status | Required Action |
|:---|:---:|:---:|:---:|:---:|:---|
| `backend/app/services/intelligence_service.py` | Base (no candidates) | + `_evaluate_candidates()` method, new imports | Teammate's own version (Phase 4.1, 171 lines, no candidate eval) | **OVERLAPPING** | Add `_evaluate_candidates()` method + imports to their file without replacing their diagnose() flow |
| `backend/app/schemas/optimization.py` | Base schemas | + `CandidateEvaluation`, `CaseProvenance`, `OutcomeVerificationState`, provenance fields on `OptimizationMemory`/`SimilarCase`/`RAGContext`, `candidate_evaluations` on `DiagnosisResult` | Their version (no provenance enums, no `CandidateEvaluation`) | **OVERLAPPING** | Append our new classes/enums; add fields to existing models |
| `backend/app/db/models.py` | No provenance cols | + 3 provenance columns on ORM model | No provenance cols | **MISSING** | Add 3 mapped columns to their `OptimizationMemoryModel` |
| `backend/app/services/memory_service.py` | No provenance filter | + `verified_only`, `provenance` params | No provenance filter | **MISSING** | Add filtering logic to `search_similar()` and `search()` |
| `backend/app/services/rag_service.py` | No provenance params | + `verified_only`, `provenance` passthrough + `verified_only` in response | No provenance params | **MISSING** | Add params to `retrieve()`, pass through, include in response |
| `backend/app/api/v1/intelligence_memory.py` | Base | Minor additions (no API route changes) | Equivalent base | **ALREADY PRESENT** | No action needed for API routes |
| `backend/app/scripts/seed_intelligence.py` | No provenance | + provenance fields in seed records | No provenance | **MISSING** | Add `provenance`, `is_verified`, `verification_state` to seed records |
| `postgres/init/03-intelligence.sql` | No provenance cols | + 3 columns + 2 indexes | No provenance cols | **MISSING** | Add columns + indexes to their DDL file |
| `postgres/init/04-intelligence-provenance-migration.sql` | Does not exist | New file | Does not exist | **MISSING** | Copy new file to their `postgres/init/` |
| `research/` directory | Pre-existing files only | Full upgraded pipeline | **Does not exist** | **RESEARCH-ONLY** | Transfer entire research directory (see Section 7) |
| `research/candidate_selector.py` | Does not exist | New file | Does not exist | **RESEARCH-ONLY** | Transfer |
| `research/measured_case_runner.py` | Does not exist | New file | Does not exist | **RESEARCH-ONLY** | Transfer |
| `research/case_schema.py` (upgraded) | 191 lines | 436 lines | Does not exist | **RESEARCH-ONLY** | Transfer |
| `research/evaluation_harness.py` (upgraded) | 130 lines | 258 lines | Does not exist | **RESEARCH-ONLY** | Transfer |
| `research/baseline_retrieval.py` (upgraded) | 178 lines | 301 lines | Does not exist | **RESEARCH-ONLY** | Transfer |
| `research/split_strategy.py` (upgraded) | 132 lines | 260 lines | Does not exist | **RESEARCH-ONLY** | Transfer |
| Phase 6–8 execution scripts & artifacts | Does not exist | Full set | Does not exist | **RESEARCH-ONLY** | Transfer |
| `frontend/` | Base | Unchanged by us | Teammate extended (RAG fields, Groq label) | **NOT REQUIRED** | Do not touch — teammate's frontend is newer |
| `backend/tests/` | Full test suite | Unchanged by us | Equivalent full test suite | **ALREADY PRESENT** | No action |
| `docker-compose.yml` | Base | Unchanged by us | Equivalent | **ALREADY PRESENT** | No action |

---

## 6. Exact Application Changes To Transfer

These are the minimum application-level changes needed in the teammate repository:

### 6.1 `backend/app/schemas/optimization.py` — ADD (do not replace entire file)

Add to the teammate's file:

```python
# New enums
class CaseProvenance(str, Enum): ...
class OutcomeVerificationState(str, Enum): ...

# New model
class CandidateEvaluation(BaseModel): ...
```

Add fields to existing models:
- `DiagnosisResult`: add `candidate_evaluations: list[CandidateEvaluation] = []`
- `OptimizationMemory`: add `provenance`, `is_verified`, `verification_state` fields
- `SimilarCase`: add `provenance`, `is_verified`, `verification_state` fields
- `RAGContext`: add `verified_only: bool = False`
- `MemorySearchRequest`: add `verified_only: bool = False`, `provenance: Optional[CaseProvenance] = None`

### 6.2 `backend/app/db/models.py` — ADD 3 columns

Add to `OptimizationMemoryModel`:
```python
provenance: Mapped[str] = mapped_column(String(50), nullable=False, default="unverified", server_default="unverified")
is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
verification_state: Mapped[str] = mapped_column(String(50), nullable=False, default="unverified", server_default="unverified")
```

### 6.3 `backend/app/services/intelligence_service.py` — ADD `_evaluate_candidates` method

Add imports:
```python
from app.schemas.optimization import BottleneckFinding, BottleneckType, CandidateEvaluation, HypotheticalIndexRequest, IndexMethod
from app.services.hypopg_validator import HypoPGValidatorService
from app.services.safety_assessor import SafetyAssessor
```

Add `_evaluate_candidates()` private method (103 lines as in our version).

In `diagnose()`, call it and assign result to `DiagnoseResponse.diagnosis.candidate_evaluations`.

### 6.4 `backend/app/services/memory_service.py` — ADD provenance filtering

In `search_similar()`: add `verified_only: bool = False` and `provenance: Optional[CaseProvenance] = None` parameters. Add filtering loop before similarity computation.

In `search()`: pass `verified_only` and `provenance` from `request` to `search_similar()`.

In `_to_memory()` and `_to_similar_case()`: read provenance fields from model using `getattr(..., "unverified")` pattern (safe for existing rows without columns).

### 6.5 `backend/app/services/rag_service.py` — ADD provenance passthrough

Add `verified_only` and `provenance` parameters to `retrieve()`. Pass to `memory_service.search_similar()`. Include `verified_only` in returned `RAGContext`.

### 6.6 `backend/app/scripts/seed_intelligence.py` — ADD provenance fields to seed records

Add to each seed case dict:
```python
"provenance": "measured",
"is_verified": True,
"verification_state": "verified_measured",
```

Update `service.create_memory()` calls to pass these fields (or update `create_memory()` to accept them).

### 6.7 `postgres/init/03-intelligence.sql` — ADD columns and indexes

Add to `optimization_memories` table definition:
```sql
provenance VARCHAR(50) NOT NULL DEFAULT 'unverified',
is_verified BOOLEAN NOT NULL DEFAULT FALSE,
verification_state VARCHAR(50) NOT NULL DEFAULT 'unverified',
```

Add indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_optimization_memories_provenance ON optimization_memories (provenance);
CREATE INDEX IF NOT EXISTS idx_optimization_memories_is_verified ON optimization_memories (is_verified);
```

### 6.8 `postgres/init/04-intelligence-provenance-migration.sql` — NEW FILE

Copy directly from our working copy. This is a new file (not present in teammate repo).

---

## 7. Research Files To Transfer

The teammate has no `research/` directory at all. The following should be transferred as a
new `research/` directory in the teammate repo root.

### 7a. Core Research Libraries (upgraded from pre-existing)

| File | Source |
|:---|:---|
| `research/case_schema.py` | `B\research\case_schema.py` (upgraded 436-line version) |
| `research/evaluation_harness.py` | `B\research\evaluation_harness.py` (upgraded 258-line version) |
| `research/baseline_retrieval.py` | `B\research\baseline_retrieval.py` (upgraded 301-line version) |
| `research/split_strategy.py` | `B\research\split_strategy.py` (upgraded 260-line version) |

### 7b. New Research Libraries

| File | Source |
|:---|:---|
| `research/candidate_selector.py` | `B\research\candidate_selector.py` |
| `research/measured_case_runner.py` | `B\research\measured_case_runner.py` |

### 7c. Pre-Existing Research Files (carry forward for completeness)

| File | Source |
|:---|:---|
| `research/ablation_study.py` | Either A or B (same) |
| `research/evaluation_framework.py` | Either A or B (same) |
| `research/harness.py` | Either A or B (same) |
| `research/metrics.py` | Either A or B (same) |
| `research/requirements.txt` | `B\research\requirements.txt` |
| `research/experiment_manifest.json` | Either A or B |
| `research/experiment_manifest.md` | Either A or B |
| `research/data/sample_cases.json` | Either A or B |
| `research/data/README.md` | Either A or B |
| `research/README.md` | Either A or B |

### 7d. Phase Execution Scripts (new, from B)

| File | Source |
|:---|:---|
| `research/execute_phase6a_corpus.py` | `B\research\` |
| `research/execute_phase6d_experiment.py` | `B\research\` |
| `research/execute_phase7.py` | `B\research\` |
| `research/execute_phase8.py` | `B\research\` |
| `research/build_partition_manifest.py` | `B\research\` |
| `research/audit_helper.py` | `B\research\` |

### 7e. Research Data / Manifests / Reports (from B — all KEEP-classified)

| File | Source |
|:---|:---|
| `research/phase6c_partition_manifest.json` | `B\research\` (**locked anchor**) |
| `research/phase6d_experiment_manifest.json` | `B\research\` |
| `research/phase6d_measurements.json` | `B\research\` |
| `research/phase6d_selection_results.json` | `B\research\` |
| `research/phase7_*.json` | `B\research\` |
| `research/phase8_*.json` | `B\research\` |
| `research/phase6a_corpus_results.json` | `B\research\` |
| `research/PHASE3_*.md` through `research/PHASE8_*.md` | `B\research\` |
| `research/HANDOFF/` | `B\research\HANDOFF\` |

### 7f. Optional Research Files

| File | Classification |
|:---|:---|
| `research/audit_dump.json` | OPTIONAL |
| `research/scratch/phase8_hash_verify.py` | OPTIONAL |
| `research/scratch/phase8_consistency_check.py` | OPTIONAL |

---

## 8. Files NOT To Transfer

| File/Category | Reason |
|:---|:---|
| `frontend/` (entire) | Teammate has newer frontend with RAG fields and Groq label fix. Do not touch. |
| `backend/tests/` | Teammate already has equivalent test suite. No research-specific tests to add. |
| `docker-compose.yml` | Teammate version is equivalent. No changes needed. |
| `backend/app/services/llm_service.py` | Unchanged by our research. |
| `backend/app/services/benchmark_service.py` | Unchanged by our research. |
| `backend/app/services/approval_service.py` | Unchanged by our research. |
| `backend/app/services/bottleneck_detector.py` | Unchanged by our research. |
| `backend/app/services/recommendation_engine.py` | Unchanged by our research. |
| `backend/app/services/remediation_service.py` | Unchanged by our research. |
| `backend/app/services/safety_assessor.py` | Unchanged by our research. |
| `backend/app/services/hypopg_validator.py` | Unchanged by our research. |
| `backend/app/core/` (all) | Unchanged by our research. |
| `backend/app/api/v1/` (except intelligence_memory additions) | Unchanged by our research. |
| `autodba-main/backend/temp_t3_variant_diagnostic.py` | Temporary debug file — do not transfer. |
| `autodba-main/backend/temp_tp_a_diagnostic.py` | Temporary debug file — do not transfer. |
| `455`, `=` (repo root stray files) | Stray shell artifacts — do not transfer. |
| Phase 1–8 `.gitignore` entry | Our research `.gitignore` covers `.venv/`, `__pycache__/` etc. Teammate likely has their own — do not overwrite. |

---

## 9. Potential Integration Risks

### RISK 1 — `intelligence_service.py` (HIGH — overlapping)

Both we and the teammate modified the original `intelligence_service.py`. Their version is
171 lines with LLM-specific improvements (Groq label, RAG field alignment, frontend fixes).
Our addition is `_evaluate_candidates()` (~100 lines) plus 6 new imports.

**Integration requirement:** The `_evaluate_candidates()` method must be added to **their**
version, not our version. Their `diagnose()` method signature and LLM behaviour must be preserved.
The integration point is: after `resolved_recommendation` is determined, call
`_evaluate_candidates()` and attach result to `DiagnoseResponse.diagnosis.candidate_evaluations`.

### RISK 2 — `schemas/optimization.py` (MEDIUM — additive but large)

Both repos have grown `optimization.py` independently. The teammate's version may have
different field names or models related to their frontend work (RAG fields alignment, Groq).
Our additions are purely additive (new classes, new fields on existing models), but care is
needed to not overwrite their field definitions.

**Integration requirement:** Diff their version against ours carefully. Insert new enums and
classes in isolated blocks. Add new fields to existing models using `Optional` with defaults
to maintain backward compatibility.

### RISK 3 — `postgres/init/03-intelligence.sql` (LOW — additive)

Their DDL is structurally identical to our original baseline but lacks provenance columns.
Adding columns with `DEFAULT` values is safe. However, if they have a running database, the
migration file (`04-*.sql`) handles the additive case idempotently.

### RISK 4 — `seed_intelligence.py` (LOW — additive)

The teammate's seed data is similar but not identical to ours. Their seeds do not include
provenance fields. Adding the fields is safe if `create_memory()` is updated to accept them.
If `create_memory()` does not accept these kwargs, a secondary update is required.

### RISK 5 — `research/` path resolution in execution scripts (MEDIUM)

Our execution scripts (`execute_phase8.py`, etc.) resolve paths relative to the script location
and expect `autodba-main/backend` to be a sibling of the `research/` directory. In the teammate
repo, the structure is flat (`backend/` directly at root with no `autodba-main/` wrapper).

**Integration requirement:** Before running any Phase 6–8 execution scripts in the teammate
repo, update the `backend_path` line:

```python
# Our version (wrong for teammate repo):
backend_path = root_path / "autodba-main" / "backend"

# Required for teammate repo:
backend_path = root_path / "backend"
```

This affects: `execute_phase6a_corpus.py`, `execute_phase6d_experiment.py`,
`execute_phase7.py`, `execute_phase8.py`, `measured_case_runner.py`, `audit_helper.py`.

---

## 10. Recommended Transfer Procedure

> **Do NOT execute until the analysis is approved.**

### Prerequisites

- Clean working trees in both B and C (`git status` = clean)
- No active experiments running against the database
- Confirm `autodba-main` (A) is untouched throughout

### Step 1 — Create a working branch in the teammate repo

```powershell
git -C "C:\Users\swarsh\Desktop\autodba-transfer" checkout -b research-upgrade
```

### Step 2 — Transfer the research directory

The teammate has no `research/` at all. Copy the entire directory (excluding temp/debug files):

```powershell
# Copy core and upgraded research libraries
Copy-Item "C:\Users\swarsh\Desktop\autodba-research\research" `
          "C:\Users\swarsh\Desktop\autodba-transfer\research" `
          -Recurse -Exclude @("scratch", "audit_dump.json")
```

Then update the 6 execution scripts to change `backend_path` from
`root_path / "autodba-main" / "backend"` to `root_path / "backend"`.

### Step 3 — Apply database schema changes

**3a. Edit** `C:\Users\swarsh\Desktop\autodba-transfer\postgres\init\03-intelligence.sql`:
  Add the 3 provenance columns and 2 indexes (exact text from our diff, Section 6.7).

**3b. Copy** `04-intelligence-provenance-migration.sql` from our version:
```powershell
Copy-Item "C:\Users\swarsh\Desktop\autodba-research\autodba-main\postgres\init\04-intelligence-provenance-migration.sql" `
          "C:\Users\swarsh\Desktop\autodba-transfer\postgres\init\"
```

### Step 4 — Apply ORM model changes

**Edit** `C:\Users\swarsh\Desktop\autodba-transfer\backend\app\db\models.py`:
Add the 3 mapped columns to `OptimizationMemoryModel` (exact definitions from Section 6.2).
Add `Boolean` to SQLAlchemy imports.

### Step 5 — Apply schema additions

**Edit** `C:\Users\swarsh\Desktop\autodba-transfer\backend\app\schemas\optimization.py`:
- Insert `CaseProvenance`, `OutcomeVerificationState` enums
- Insert `CandidateEvaluation` model
- Add provenance fields to `OptimizationMemory`, `SimilarCase`
- Add `verified_only` to `RAGContext`
- Add `candidate_evaluations` to `DiagnosisResult`
- Add `verified_only`, `provenance` to `MemorySearchRequest`

Use `Optional` with defaults throughout for backward compatibility.

### Step 6 — Apply service changes

**Edit** `backend/app/services/memory_service.py`:
Add `verified_only` and `provenance` parameters to `search_similar()` and `search()`.
Add provenance-aware field reads in `_to_memory()` and `_to_similar_case()`.

**Edit** `backend/app/services/rag_service.py`:
Add `verified_only` and `provenance` params to `retrieve()`, pass through, return in `RAGContext`.

**Edit** `backend/app/scripts/seed_intelligence.py`:
Add provenance fields to each seed case dict.

### Step 7 — Integrate `_evaluate_candidates` into teammate's `intelligence_service.py`

**Edit** their `intelligence_service.py` (do NOT replace the file):
- Add 5 new imports at top
- Add `_evaluate_candidates()` method body after the existing `_generate_explanation()` method
- In `diagnose()`, call it after `resolved_recommendation` and attach to `candidate_evaluations`

### Step 8 — Commit on the branch

```powershell
git -C "C:\Users\swarsh\Desktop\autodba-transfer" add .
git -C "C:\Users\swarsh\Desktop\autodba-transfer" commit -m "research: add Phase 1-8 provenance, candidate evaluation, and research pipeline"
```

### Step 9 — Open a pull request for review before merging to main

Do not merge directly. Let the team review.

---

## 11. Verification Plan

After integration, verify:

### Teammate functionality intact

1. `frontend/` — build/run frontend; verify RAG fields and Groq label still work
2. `backend/` — run `pytest backend/tests/` — all pre-existing tests should still pass
3. `GET /api/v1/intelligence/memories` — returns existing memories correctly
4. `POST /api/v1/intelligence/diagnose` — returns response with new `candidate_evaluations` field (can be empty array for non-MISSING_INDEX queries)

### Our research upgrades present

1. `from backend.app.schemas.optimization import CandidateEvaluation, CaseProvenance` — succeeds
2. `from research.candidate_selector import CandidateSelector` — succeeds
3. `from research.case_schema import canonicalize_sql, compute_template_hash` — succeeds
4. `from research.measured_case_runner import ResearchSafetyError` — succeeds
5. Run `python research/scratch/phase8_consistency_check.py` (after path fix) — all PASS

### Pipeline still works

1. `python -m research.execute_phase8` (after `backend_path` fix) — runs cleanly
2. Verify `optimization_memories` still has 14 rows
3. Verify zero residual `idx_autodba_*` indexes

### Original reference intact

```powershell
# Verify A is unmodified — compare file counts
(Get-ChildItem "C:\Users\swarsh\Desktop\autodba-main" -Recurse -File).Count
# Should match pre-analysis count; no files should have changed
```

---

## 12. Final Verdict

**"Exactly what should we push to the teammate repository?"**

### YES — push the following:

1. **A new `research/` directory** containing all upgraded research libraries
   (`case_schema.py`, `candidate_selector.py`, `split_strategy.py`, `evaluation_harness.py`,
   `baseline_retrieval.py`, `measured_case_runner.py`) plus all Phase 3–8 artifacts,
   execution scripts, and manifests. With path fix for `backend_path`.

2. **Database provenance schema** (`postgres/init/03-intelligence.sql` updated,
   `postgres/init/04-intelligence-provenance-migration.sql` new).

3. **ORM model provenance columns** (`backend/app/db/models.py` — 3 new mapped columns).

4. **New schema types** (`backend/app/schemas/optimization.py` — 3 new classes/enums, new
   fields on 5 existing models).

5. **Intelligence service candidate evaluation** (`backend/app/services/intelligence_service.py`
   — `_evaluate_candidates()` method + 5 imports + call site in `diagnose()`).

6. **Memory/RAG provenance filtering** (`backend/app/services/memory_service.py`,
   `backend/app/services/rag_service.py`).

7. **Seed data provenance fields** (`backend/app/scripts/seed_intelligence.py`).

### Do NOT push:

- `frontend/` — teammate's is newer and should not be touched
- `backend/tests/` — no research-specific tests; teammate's suite is equivalent
- `docker-compose.yml` — no changes needed
- Any unchanged backend service files
- Temp/debug files (`455`, `=`, `temp_*.py`)
- `.gitignore` — let teammate manage theirs

### Integration method required:

**Do not copy-replace** `intelligence_service.py` or `schemas/optimization.py`. Both files
have overlapping teammate changes. These require **semantic integration** (targeted edits)
rather than wholesale file replacement.

---

*Analysis completed: 2026-10-03. No files were modified in any of the three directories.*
