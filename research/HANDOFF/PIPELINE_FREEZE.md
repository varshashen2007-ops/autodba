# AutoDBA Research Pipeline — Freeze Document

**Freeze date:** 2026-10-03  
**Freeze type:** Reference checkpoint before repository transfer  
**Repository:** `C:\Users\swarsh\Desktop\autodba-research`  
**HEAD commit:** `2fec570` — `research: validate first measured pilot pipeline`

This document records the exact state of the AutoDBA research pipeline at the time of freeze.
It is a factual record, not a set of rules for future development.

---

## 1. What This Freeze Is

A snapshot of a known-working research pipeline that has been validated end-to-end through
Phase 8. Future developers may modify, replace, extend, or remove any part of this system.

---

## 2. Repository Structure

```
autodba-research/
├── autodba-main/               ← Production backend (Docker-based)
│   └── backend/
│       └── app/
│           ├── services/       ← intelligence_service, benchmark_service, etc.
│           └── schemas/        ← optimization.py (DiagnoseRequest, CandidateEvaluation…)
├── research/                   ← All research pipeline code and artifacts
│   ├── case_schema.py          ← OptimizationCase, canonicalize_sql, compute_template_hash
│   ├── candidate_selector.py   ← Policy A/B/C, CandidateSelector, canonical_candidate_key
│   ├── split_strategy.py       ← grouped_template_split, verify_split_leakage
│   ├── evaluation_harness.py   ← EvaluationHarness, RetrievalResult
│   ├── baseline_retrieval.py   ← BaselineRetrievalMethods, compute_token_hash_similarity
│   ├── measured_case_runner.py ← MeasuredCaseRunner, ResearchSafetyError
│   └── HANDOFF/                ← This directory
└── .gitignore
```

---

## 3. Validated Commits (Frozen Git History)

All 8 research commits exist and have been verified:

| Short SHA | Commit Message | Date |
|:---:|:---|:---:|
| `4b92f1c` | baseline: preserve original AutoDBA project before research upgrades | 2026-10-01 |
| `012a285` | phase1: deterministic candidate evaluation for missing index findings | 2026-10-01 |
| `711d1da` | research: add provenance-aware historical memory | 2026-10-01 |
| `ca20fda` | phase3: establish leakage-controlled evaluation boundary | 2026-10-01 |
| `bd64709` | phase4: add outcome-aware candidate selection framework | 2026-10-01 |
| `9823441` | phase5b: add controlled measured-case runner | 2026-10-01 |
| `4b7a616` | phase5c: document research database readiness blocker | 2026-10-01 |
| `f9f1152` | phase5d: finalize first pilot execution audit | 2026-10-01 |
| **`2fec570`** | **research: validate first measured pilot pipeline** ← **HEAD** | 2026-10-01 |

**The HEAD is `2fec570`. No tracked files have been modified since HEAD** (`git diff HEAD` = empty).

---

## 4. Uncommitted Research Artifacts (Part of the Frozen State)

All files below are untracked (`??`) by git but constitute the validated research work.
They were generated during Phases 6, 7, and 8 and form the complete validated record.

### Phase 6 Artifacts

| File | Classification | Description |
|:---|:---:|:---|
| `research/PHASE6_EXPERIMENT_DESIGN.md` | **KEEP** | Full Phase 6 experiment specification |
| `research/PHASE6A_CORPUS_CANDIDATE_MANIFEST.md` | **KEEP** | Phase 6A corpus candidate analysis |
| `research/PHASE6A_CORPUS_EXECUTION_REPORT.md` | **KEEP** | Phase 6A execution results |
| `research/PHASE6B_CORPUS_QUALITY_AUDIT.md` | **KEEP** | Phase 6B data quality audit |
| `research/PHASE6C_PARTITION_LOCK.md` | **KEEP** | Phase 6C partition lock specification |
| `research/PHASE6D_AUDIT.md` | **KEEP** | Phase 6D execution audit |
| `research/PHASE6D_COMPARATIVE_EXECUTION_REPORT.md` | **KEEP** | Phase 6D A/B/C vs oracle results |
| `research/phase6a_corpus_results.json` | **KEEP** | Phase 6A machine-readable corpus results |
| `research/phase6c_partition_manifest.json` | **KEEP** | **Authoritative partition manifest (SHA-256 locked)** |
| `research/phase6d_experiment_manifest.json` | **KEEP** | Phase 6D frozen hyperparameters |
| `research/phase6d_measurements.json` | **KEEP** | Phase 6D benchmark results |
| `research/phase6d_selection_results.json` | **KEEP** | Phase 6D frozen policy selections |

### Phase 6 Execution Scripts

| File | Classification | Description |
|:---|:---:|:---|
| `research/execute_phase6a_corpus.py` | **KEEP** | Phase 6A corpus runner |
| `research/execute_phase6d_experiment.py` | **KEEP** | Phase 6D A/B/C comparative runner |
| `research/build_partition_manifest.py` | **KEEP** | Partition manifest builder |

### Phase 7 Artifacts

| File | Classification | Description |
|:---|:---:|:---|
| `research/PHASE7_CANDIDATE_SUPPORT_MATRIX.md` | **KEEP** | Candidate support analysis |
| `research/PHASE7_CORPUS_DESIGN_AUDIT.md` | **KEEP** | Corpus design audit |
| `research/PHASE7_EXECUTION_REPORT.md` | **KEEP** | Phase 7 execution results |
| `research/PHASE7_AUDIT.md` | **KEEP** | Phase 7 invariant audit |
| `research/phase7_corpus_design_manifest.json` | **KEEP** | Phase 7 corpus design |
| `research/phase7_experiment_manifest.json` | **KEEP** | Phase 7 experiment manifest |
| `research/phase7_measurements.json` | **KEEP** | Phase 7 benchmark results |
| `research/phase7_selection_results.json` | **KEEP** | Phase 7 frozen policy selections |
| `research/execute_phase7.py` | **KEEP** | Phase 7 execution script |

### Phase 8 Artifacts

| File | Classification | Description |
|:---|:---:|:---|
| `research/PHASE8_MULTI_CANDIDATE_DESIGN.md` | **KEEP** | Phase 8 experiment design |
| `research/PHASE8_PRE_EXECUTION_AUDIT.md` | **KEEP** | Phase 8 pre-execution audit |
| `research/phase8_experiment_manifest.json` | **KEEP** | Phase 8 frozen manifest |
| `research/phase8_selection_results.json` | **KEEP** | Frozen selections (pre-measurement) |
| `research/phase8_measurements.json` | **KEEP** | Phase 8 benchmark results |
| `research/PHASE8_EXECUTION_REPORT.md` | **KEEP** | Phase 8 execution report |
| `research/PHASE8_FINAL_AUDIT.md` | **KEEP** | Phase 8 invariant audit |
| `research/execute_phase8.py` | **KEEP** | Phase 8 execution script |

### Utility / Debug / Temporary Files

| File | Classification | Description |
|:---|:---:|:---|
| `research/audit_dump.json` | **OPTIONAL** | Debug dump from earlier audit work |
| `research/audit_helper.py` | **OPTIONAL** | One-off audit helper script |
| `research/scratch/phase8_hash_verify.py` | **OPTIONAL** | Hash verification script (read-only) |
| `research/scratch/phase8_consistency_check.py` | **OPTIONAL** | Artifact consistency checker |
| `autodba-main/backend/temp_t3_variant_diagnostic.py` | **REMOVE BEFORE TRANSFER** | Temporary T3 diagnostic in backend dir |
| `autodba-main/backend/temp_tp_a_diagnostic.py` | **REMOVE BEFORE TRANSFER** | Temporary TP-A diagnostic in backend dir |
| `455` (repo root) | **REMOVE BEFORE TRANSFER** | Stray file at repo root |
| `=` (repo root) | **REMOVE BEFORE TRANSFER** | Stray file at repo root (likely from `>>=` shell redirect) |

### Pre-Phase-6 Research Files (tracked by git via HEAD commits)

These are tracked in git and do not need separate attention:

- `research/baseline_retrieval.py`, `candidate_selector.py`, `case_schema.py`
- `research/evaluation_harness.py`, `split_strategy.py`, `measured_case_runner.py`
- `research/PHASE3_*`, `PHASE4_*`, `PHASE5*` markdown files
- `research/ablation_study.py`, `evaluation_framework.py`, `harness.py`, `metrics.py`
- `research/experiment_manifest.json`, `experiment_manifest.md`
- `research/data/sample_cases.json`

---

## 5. Pipeline Architecture

The validated pipeline has five logical layers:

```
Layer 1 — Production Diagnosis
  IntelligenceService.diagnose()
      Phase 1: extract predicates, generate candidate indexes
      HypoPG: simulate costs, validate candidates
      SafetyAssessor: gate on safety eligibility

Layer 2 — Research Case Representation
  case_schema.py: OptimizationCase, canonicalize_sql, compute_template_hash
  Provenance: measured / real_measured / simulated / generated

Layer 3 — Partition & Leakage Control
  split_strategy.py: grouped_template_split (by template hash), verify_split_leakage
  Partition lock: SHA-256 of phase6c_partition_manifest.json

Layer 4 — Candidate Selection Policies
  candidate_selector.py: CandidateSelector
      Policy A: select_planner_only (is_baseline = True)
      Policy B: select_similarity (HypoPG% + alpha*sim_support)
      Policy C: select_outcome_aware (HypoPG% + beta*outcome_support, lambda_reg penalty)

Layer 5 — Physical Measurement & Oracle
  measured_case_runner.py / execute_phase*.py:
      W=2 warmup, N=10 measured (mean latency)
      Oracle = argmax(runtime_improvement_percent) over all eligible candidates
      Selection locked before measurement; oracle determined post-hoc
```

---

## 6. Phase 8 Result (T9 Case)

**Query:** `SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00`  
**Template (T9):** `select * from orders where customer_id = ? and total_amount >= ?`  
**Template hash:** `8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343`

| Candidate | HypoPG% | Measured dT% | Oracle? |
|:---|:---:|:---:|:---:|
| `orders(total_amount, customer_id)` | 87.55% | **+56.55%** | **YES** |
| `orders(customer_id)` | 76.52% | +42.08% | No |
| `orders(total_amount)` | 53.70% | +35.38% | No |

**Policy A/B/C selections: all composite. Regret: 0.00%. Oracle agreement: 100%.**

**This is N=1.** It validates that the pipeline executes correctly with multiple candidates and
that selections are properly frozen before measurement. It does not establish that any policy
is superior to another.

---

## 7. Locked Constants

| Constant | Value | Source |
|:---|:---:|:---|
| Phase 6C partition SHA-256 | `b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27` | Phase 6C lock |
| alpha (Policy B) | 1.0 | Phase 6D |
| beta (Policy C) | 1.0 | Phase 6D |
| lambda_reg | 1.5 | Phase 6D |
| TRAIN memory IDs | 1–6 | Phase 6C |
| Benchmark protocol | W=2, N=10 | Phase 6D |
| Experiment seed | 42 | Phase 6C |

---

## 8. What Has Been Demonstrated

- A functional end-to-end pipeline from raw SQL → candidate generation → HypoPG validation →
  safety gate → policy selection → physical benchmark → oracle comparison.
- Template-hash-based train/test partitioning with verified leakage controls.
- Outcome-aware and similarity-based policies (B, C) access TRAIN evidence without leaking
  TEST outcomes into the retrieval corpus.
- Physical benchmark cleanup (DROP INDEX + DISCARD ALL) with pre/post residual checks.
- `optimization_memories` count invariant maintained across all experiments.
- Correct policy selection timestamp preceding physical measurement.
- HypoPG cost improvement systematically overestimates physical dT% (consistent across phases).
- HypoPG ordinal ranking matches physical ranking in all validated cases.

## 9. What Has NOT Been Demonstrated

- Statistical superiority of Policy B or C over Policy A. No case of policy divergence has
  been observed (Phase 6D: 3/5 cases were single-candidate; Phase 7: all 5 single-candidate;
  Phase 8: unanimous agreement).
- Generalizability across different tables, query patterns, or workloads.
- Scalability to large corpora or high-concurrency environments.
- Production deployment safety (the system was tested on an isolated research instance).

---

## 10. Reference Checkpoint Statement

This freeze constitutes a **reference checkpoint** of the AutoDBA research pipeline as of
2026-10-03. It records the state at which the pipeline was validated to run correctly end-to-end
through Phase 8.

It is not a claim of research finality, policy superiority, or production readiness.
The future development team may modify any part of this system.
