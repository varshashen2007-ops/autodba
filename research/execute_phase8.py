"""
Phase 8: Multi-Candidate Unseen-Template Experiment
====================================================
Executes the full A/B/C comparative selection and oracle evaluation for the
T9 case:

    SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00

STRICT INVARIANTS (identical to Phase 6D / Phase 7):
  1. Preflight: Phase 6C SHA-256 verified, optimization_memories=14, 0 residual indexes.
  2. T9 template confirmed absent from existing corpus before execution.
  3. Phase 1 candidate generation via authoritative IntelligenceService (no mocks).
  4. Offline policy selection (A/B/C) LOCKED before any physical measurement.
  5. EVERY eligible candidate independently measured (W=2, N=10 protocol).
  6. Oracle determined AFTER all measurements complete.
  7. Zero optimization_memories mutations during experiment.
  8. TRAIN retrieval strictly limited to Memory IDs 1-6.
  9. All experimental indexes dropped; DISCARD ALL after each measurement.
 10. Phase 6C, 6D, Phase 7 artifacts untouched.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

root_path = Path(__file__).resolve().parent.parent
backend_path = root_path / "backend"
research_path = root_path / "research"

for p in [str(root_path), str(backend_path)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("POSTGRES_HOST", "localhost")

from sqlalchemy import text
from app.db.database import SessionLocal, engine
from app.schemas.optimization import DiagnoseRequest
from app.services.intelligence_service import IntelligenceService
from app.services.llm_service import LLMProvider, LLMService

from research.case_schema import (
    OptimizationCase,
    IncidentType,
    QueryInfo,
    PlanInfo,
    RecommendationAction,
    HypoPGValidation,
    MeasuredOutcome,
    MeasurementQualityInfo,
    canonicalize_sql,
    compute_template_hash,
)
from research.candidate_selector import (
    CandidateSelector,
    canonical_candidate_key,
    extract_candidate_key,
)
from research.measured_case_runner import ResearchSafetyError

# ─────────────────────────────────────────────────────────────────────────────
# Constants — all locked from prior phases
# ─────────────────────────────────────────────────────────────────────────────

PHASE6C_SHA256 = "b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27"
TRAIN_MEMORY_IDS = [1, 2, 3, 4, 5, 6]

# Frozen hyperparameters (from phase6d_experiment_manifest.json)
ALPHA = 1.0
BETA = 1.0
LAMBDA_REG = 1.5
WARMUP_RUNS = 2
MEASURED_RUNS = 10

# T9 case definition
T9_CASE = {
    "case_id": "CASE-T9-01",
    "template_id": "T9",
    "sql": "SELECT * FROM orders WHERE customer_id = 42 AND total_amount >= 450.00",
    "target_table": "orders",
}

# Verified T9 template hash (computed in phase8_hash_verify.py)
T9_EXPECTED_HASH = "8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343"

# All existing template hashes (must not include T9)
EXISTING_TEMPLATE_HASHES = {
    "T1": "036cb1ede04b97e1c6f74baa1d4fdce5cbfb6cca2ad7c64a8018d1c4f608a636",
    "T2": "f5bbbbeea30650c2c997aeadc2230f1b37fe979559019aba0304bf15730e563c",
    "T3": "30a0565175c281388d71d94a46e18432d582b204efaa478e88d86c3166ce39b2",
    "T5": "6bcb778b583d7913410164211ea7137d5bd13ddf49daa252854435e899666b58",
    "T7": "03fe9bcb608dbc9323c5744caf0518171dd12a199fc66d8af319daf545ae6b64",
    "T8": "3c098f93b8db0d86bd20843c7d4361b26048ab6e3484d8a878418d05e2e0556c",
}


class _DetProvider(LLMProvider):
    """Deterministic no-op LLM provider for research execution."""
    def explain(self, *, query, diagnosis, recommendation, similar_cases):
        return "Deterministic Phase 8 research run."


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def count_autodba_indexes() -> int:
    with engine.connect() as conn:
        return int(conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%'")
        ).scalar() or 0)


def load_train_cases() -> List[OptimizationCase]:
    """Load strictly TRAIN cases (Memory IDs 1–6) from optimization_memories."""
    cases = []
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT id, incident_type, query_text, diagnosis, recommendation, "
                "validation, benchmark, outcome, provenance, is_verified, verification_state "
                "FROM optimization_memories WHERE id = ANY(:mids) ORDER BY id"
            ),
            {"mids": TRAIN_MEMORY_IDS},
        ).mappings().fetchall()

        for r in rows:
            bm = r["benchmark"] or {}
            b_before = bm.get("before") or {}
            b_after = bm.get("after") or {}
            rec = r["recommendation"] or {}
            val = r["validation"] or {}

            opt_case = OptimizationCase(
                case_id=f"MEM_{r['id']}",
                incident_type=IncidentType.MISSING_INDEX,
                query=QueryInfo(text=r["query_text"]),
                plan=PlanInfo(raw_plan=r["diagnosis"] or {}),
                recommendation=RecommendationAction(
                    action_type="create_index",
                    table=rec.get("relation"),
                    columns=rec.get("columns", []),
                    index_method=rec.get("index_method", "btree"),
                    sql_preview=rec.get("sql_preview", ""),
                ),
                hypopg_validation=HypoPGValidation(
                    hypopg_validated=bool(val.get("hypopg_validated", True)),
                    cost_improvement_percent=val.get("cost_improvement_percent", 0.0),
                ),
                measured_outcome=MeasuredOutcome(
                    before_runtime_ms=b_before.get("mean_execution_time_ms"),
                    after_runtime_ms=b_after.get("mean_execution_time_ms"),
                    runtime_improvement_percent=bm.get("runtime_improvement_percent"),
                    planner_cost_improvement_percent=bm.get("planner_cost_improvement_percent"),
                    benchmark_status="completed",
                ),
                measurement_quality=MeasurementQualityInfo(
                    runs_executed=b_after.get("runs", 10),
                    warmup_runs_discarded=b_after.get("warmup_runs", 2),
                    coefficient_of_variation=b_after.get("coefficient_of_variation"),
                    validation_completed=True,
                ),
                provenance="measured",
                is_verified=True,
                verification_state="verified_measured",
            )
            cases.append(opt_case)
    return cases


def benchmark_candidate(
    query: str,
    table: str,
    columns: List[str],
    candidate_label: str,
    warmup_runs: int = WARMUP_RUNS,
    measured_runs: int = MEASURED_RUNS,
) -> Dict[str, Any]:
    """
    Physically benchmarks ONE candidate index in isolation.
    Protocol: W=2 warmup, N=10 measured. Index prefix: idx_autodba_p8_
    Pre-flight and post-cleanup zero-index checks enforced.
    """
    pre_residual = count_autodba_indexes()
    if pre_residual > 0:
        raise ResearchSafetyError(
            f"Pre-flight failed: {pre_residual} residual idx_autodba_* indexes present!"
        )

    clean_cols = [c.strip().lower() for c in columns if c and c.strip()]
    col_str = "_".join(clean_cols)
    idx_name = f"idx_autodba_p8_{table.lower()}_{col_str}"
    cols_ddl = ", ".join(clean_cols)

    db = SessionLocal()
    try:
        # === Step A: Baseline measurement (index scans disabled) ===
        db.execute(text("SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off;"))
        t_before_samples = []
        for _ in range(warmup_runs):
            db.execute(text(query)).fetchall()
        for _ in range(measured_runs):
            t0 = time.perf_counter()
            db.execute(text(query)).fetchall()
            t1 = time.perf_counter()
            t_before_samples.append((t1 - t0) * 1000.0)

        explain_before = db.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
        ).scalar()
        db.rollback()

        # === Step B: Create candidate index ===
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as ddl_conn:
            ddl_conn.execute(text(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} ON {table} ({cols_ddl});"
            ))

        # Verify index was created
        with engine.connect() as chk:
            idx_exists = chk.execute(
                text("SELECT COUNT(*) FROM pg_indexes WHERE indexname = :n"),
                {"n": idx_name},
            ).scalar()
            if not idx_exists:
                raise RuntimeError(f"Index {idx_name} creation failed.")

        # === Step C: Post-index measurement (index scans enabled) ===
        db.execute(text("SET LOCAL enable_indexscan = on; SET LOCAL enable_bitmapscan = on;"))
        t_after_samples = []
        for _ in range(warmup_runs):
            db.execute(text(query)).fetchall()
        for _ in range(measured_runs):
            t0 = time.perf_counter()
            db.execute(text(query)).fetchall()
            t1 = time.perf_counter()
            t_after_samples.append((t1 - t0) * 1000.0)

        explain_after = db.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
        ).scalar()
        db.rollback()

    finally:
        # === Step D: Teardown ===
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as cl:
            cl.execute(text(f"DROP INDEX IF EXISTS {idx_name};"))
            cl.execute(text("DISCARD ALL;"))
        db.close()

    # === Step E: Post-cleanup verification ===
    post_residual = count_autodba_indexes()
    cleanup_success = (post_residual == 0)

    # Statistics
    mean_before = sum(t_before_samples) / len(t_before_samples)
    sd_before = math.sqrt(
        sum((x - mean_before) ** 2 for x in t_before_samples) / len(t_before_samples)
    )
    cov_before = sd_before / mean_before if mean_before > 0 else 0.0

    mean_after = sum(t_after_samples) / len(t_after_samples)
    sd_after = math.sqrt(
        sum((x - mean_after) ** 2 for x in t_after_samples) / len(t_after_samples)
    )
    cov_after = sd_after / mean_after if mean_after > 0 else 0.0

    delta_t_pct = (
        (mean_before - mean_after) / mean_before * 100.0 if mean_before > 0 else 0.0
    )

    plan_b = explain_before[0]["Plan"] if isinstance(explain_before, list) and explain_before else {}
    plan_a = explain_after[0]["Plan"] if isinstance(explain_after, list) and explain_after else {}

    return {
        "index_name": idx_name,
        "target_table": table,
        "target_columns": clean_cols,
        "candidate_label": candidate_label,
        "t_before_ms": round(mean_before, 4),
        "t_after_ms": round(mean_after, 4),
        "t_before_samples_ms": [round(x, 4) for x in t_before_samples],
        "t_after_samples_ms": [round(x, 4) for x in t_after_samples],
        "cov_before": round(cov_before, 4),
        "cov_after": round(cov_after, 4),
        "runtime_improvement_percent": round(delta_t_pct, 2),
        "scan_type_before": plan_b.get("Node Type"),
        "scan_type_after": plan_a.get("Node Type"),
        "shared_hit_blocks_before": plan_b.get("Shared Hit Blocks", 0),
        "shared_hit_blocks_after": plan_a.get("Shared Hit Blocks", 0),
        "cleanup_success": cleanup_success,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def run_phase8():
    print("=" * 80)
    print("PHASE 8: MULTI-CANDIDATE UNSEEN-TEMPLATE EXPERIMENT")
    print("=" * 80)
    run_timestamp = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 0: PREFLIGHT CHECKS
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 0: PREFLIGHT CHECKS")
    print("=" * 70)

    # 0a. Phase 6C partition manifest hash
    p6c_path = research_path / "phase6c_partition_manifest.json"
    actual_sha = hashlib.sha256(p6c_path.read_bytes()).hexdigest()
    if actual_sha != PHASE6C_SHA256:
        raise RuntimeError(
            f"BLOCKER: Phase 6C manifest hash MISMATCH!\n"
            f"  Expected: {PHASE6C_SHA256}\n"
            f"  Actual:   {actual_sha}"
        )
    print(f"[OK] Phase 6C partition manifest hash verified: {actual_sha[:20]}...")

    # 0b. optimization_memories count and integrity
    with engine.connect() as conn:
        mem_count = conn.execute(text("SELECT COUNT(*) FROM optimization_memories")).scalar()
        mem_rows = conn.execute(
            text("SELECT id, provenance, is_verified, verification_state "
                 "FROM optimization_memories ORDER BY id")
        ).fetchall()

    if mem_count != 14:
        raise RuntimeError(
            f"BLOCKER: optimization_memories count = {mem_count}, expected 14."
        )
    ids_present = [r[0] for r in mem_rows]
    if sorted(ids_present) != list(range(1, 15)):
        raise RuntimeError(f"BLOCKER: Memory IDs not [1..14]. Found: {ids_present}")
    for r in mem_rows:
        if r[1] != "measured" or not r[2] or r[3] != "verified_measured":
            raise RuntimeError(
                f"BLOCKER: Memory ID {r[0]} has unexpected provenance state: {dict(r)}"
            )
    print(f"[OK] optimization_memories: {mem_count} rows, IDs 1–14, all MEASURED+VERIFIED.")

    # 0c. T9 template hash verified absent from corpus
    t9_actual_hash = compute_template_hash(T9_CASE["sql"])
    if t9_actual_hash != T9_EXPECTED_HASH:
        raise RuntimeError(
            f"BLOCKER: T9 hash mismatch — implementation may have changed!\n"
            f"  Expected: {T9_EXPECTED_HASH}\n"
            f"  Actual:   {t9_actual_hash}"
        )
    for tpl_id, tpl_hash in EXISTING_TEMPLATE_HASHES.items():
        if t9_actual_hash == tpl_hash:
            raise RuntimeError(
                f"BLOCKER: T9 hash collides with existing template {tpl_id}! "
                "T9 is not an unseen template."
            )
    print(f"[OK] T9 hash {t9_actual_hash[:20]}... absent from all existing templates.")

    # 0d. No residual idx_autodba_* indexes
    start_residual = count_autodba_indexes()
    if start_residual != 0:
        raise ResearchSafetyError(
            f"BLOCKER: {start_residual} residual idx_autodba_* indexes present at start."
        )
    print("[OK] Zero residual idx_autodba_* indexes.")

    # 0e. HypoPG + DB health check
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT hypopg_reset()"))
            print("[OK] HypoPG responsive.")
        except Exception as e:
            raise RuntimeError(f"BLOCKER: HypoPG not available: {e}")
        try:
            row_ct = conn.execute(text("SELECT COUNT(*) FROM orders")).scalar()
            print(f"[OK] Database healthy — orders table has {row_ct} rows.")
        except Exception as e:
            raise RuntimeError(f"BLOCKER: orders table not accessible: {e}")

    t9_canonical = canonicalize_sql(T9_CASE["sql"])
    print(f"\n[CONFIRMED] All 5 preflight checks PASSED.")
    print(f"  T9 canonical template: {t9_canonical!r}")
    print(f"  T9 template hash:      {t9_actual_hash}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: CANDIDATE GENERATION (Phase 1 via authoritative IntelligenceService)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 1: CANDIDATE GENERATION (Authoritative Phase 1 Diagnosis)")
    print("=" * 70)

    llm = LLMService(provider=_DetProvider())
    preflight_result = {}

    with SessionLocal() as db:
        intel = IntelligenceService(db, llm_service=llm)
        db.rollback()

        sql = T9_CASE["sql"]
        print(f"\n  Query: {sql}")

        try:
            diag = intel.diagnose(
                request=DiagnoseRequest(
                    query=sql,
                    incident_type="missing_index",
                    include_rag=False,
                )
            )
        except Exception as e:
            raise RuntimeError(f"BLOCKER: Phase 1 diagnose() failed: {e}")

        candidates = diag.diagnosis.candidate_evaluations or []
        print(f"  Phase 1 generated {len(candidates)} candidate(s):")

        all_candidates = []
        eligible = []

        for ce in candidates:
            rec = ce.recommendation
            sa = ce.safety_assessment
            cols = list(rec.columns or [])
            table_name = (rec.relation or "").lower()
            key = f"{table_name}:btree:{','.join(c.lower() for c in cols)}"

            # HypoPG verdict
            hypo_verdict = "N/A"
            hypo_pct = None
            if ce.validation:
                v = ce.validation.verdict
                hypo_verdict = v.value if hasattr(v, "value") else str(v)
                if ce.validation.comparison:
                    hypo_pct = ce.validation.comparison.cost_improvement_percent

            hypo_ok = hypo_verdict == "validated"
            safety_ok = bool(sa and sa.eligible_for_approval)
            blocking = list(sa.blocking_reasons) if (sa and sa.blocking_reasons) else []

            pct_str = f"{hypo_pct:.2f}%" if hypo_pct is not None else "N/A"
            status_tag = "ELIGIBLE" if (hypo_ok and safety_ok) else "EXCLUDED"

            print(f"    {status_tag}: {key}")
            print(f"      is_baseline={ce.is_baseline} | HypoPG={hypo_verdict}({pct_str})"
                  f" | safety={safety_ok}"
                  + (f" | blocking={blocking}" if blocking else ""))

            cand_dict = {
                "candidate_id": ce.candidate_id,
                "columns": cols,
                "canonical_key": key,
                "is_baseline": ce.is_baseline,
                "hypopg_cost_improvement": round(hypo_pct or 0.0, 2),
                "hypopg_verdict": hypo_verdict,
                "safety_eligible": safety_ok,
                "blocking_reasons": blocking,
                "recommendation": {
                    "table": table_name,
                    "columns": cols,
                    "index_method": "btree",
                },
                "validation": {
                    "cost_improvement_percent": round(hypo_pct or 0.0, 2),
                    "hypopg_validated": hypo_ok,
                },
            }
            all_candidates.append(cand_dict)
            if hypo_ok and safety_ok:
                eligible.append(cand_dict)

    has_baseline = any(c["is_baseline"] for c in eligible)
    multi_cand = len(eligible) >= 2

    print(f"\n  Total candidates from Phase 1: {len(all_candidates)}")
    print(f"  Eligible (HypoPG + safety): {len(eligible)}")
    print(f"  Multi-candidate: {multi_cand}")
    print(f"  Has baseline in eligible pool: {has_baseline}")

    if len(eligible) == 0:
        raise RuntimeError(
            "BLOCKER: Zero eligible candidates. Cannot proceed with Phase 8 experiment."
        )
    if not has_baseline:
        raise RuntimeError(
            "BLOCKER: No is_baseline==True candidate in eligible pool. "
            "Policy A requires exactly one baseline."
        )

    preflight_result = {
        "case_id": T9_CASE["case_id"],
        "template_id": T9_CASE["template_id"],
        "sql": sql,
        "canonical_template": t9_canonical,
        "template_hash": t9_actual_hash,
        "target_table": T9_CASE["target_table"],
        "total_candidates_from_phase1": len(all_candidates),
        "all_candidates": all_candidates,
        "eligible_candidates": eligible,
        "eligible_count": len(eligible),
        "multi_candidate": multi_cand,
        "has_baseline": has_baseline,
        "preflight_pass": True,
    }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: LOAD TRAIN CASES
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 2: LOAD TRAIN RETRIEVAL CORPUS (Memory IDs 1–6 ONLY)")
    print("=" * 70)

    train_cases = load_train_cases()
    print(f"  Loaded {len(train_cases)} TRAIN cases (IDs {TRAIN_MEMORY_IDS})")
    for tc in train_cases:
        print(f"    MEM_{tc.case_id.split('_')[-1]}: {tc.query.text[:60]!r} "
              f"-> cols={tc.recommendation.columns}")

    if len(train_cases) != 6:
        raise RuntimeError(
            f"BLOCKER: Expected 6 TRAIN cases, got {len(train_cases)}."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3: OFFLINE POLICY SELECTION (MUST PRECEDE ALL PHYSICAL MEASUREMENT)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3: OFFLINE POLICY SELECTION (LOCKED BEFORE PHYSICAL MEASUREMENT)")
    print("=" * 70)

    selector = CandidateSelector(alpha=ALPHA, beta=BETA, lambda_reg=LAMBDA_REG)

    print(f"\n  Hyperparameters (frozen from Phase 6D):")
    print(f"    alpha      = {ALPHA}")
    print(f"    beta       = {BETA}")
    print(f"    lambda_reg = {LAMBDA_REG}")
    print(f"\n  Candidate pool for T9:")
    for c in eligible:
        print(f"    {c['canonical_key']} | is_baseline={c['is_baseline']} "
              f"| HypoPG={c['hypopg_cost_improvement']}%")

    res_a = selector.select_planner_only(eligible)
    res_b = selector.select_similarity(sql, eligible, train_cases)
    res_c = selector.select_outcome_aware(sql, eligible, train_cases)

    def _fmt_sel(res):
        return {
            "selected_candidate_id": res.selected_candidate_id,
            "fallback_used": res.fallback_used,
            "fallback_reason": res.fallback_reason,
            "historical_support": res.historical_support,
            "lambda_reg": res.lambda_reg,
            "candidate_scores": [
                {
                    "candidate_id": cs.candidate_id,
                    "canonical_key": f"{cs.canonical_key[0]}:btree:{','.join(cs.canonical_key[2])}",
                    "is_baseline": cs.is_baseline,
                    "hypopg_cost_improvement": round(cs.hypopg_cost_improvement, 4),
                    "similarity_support": round(cs.similarity_support, 4),
                    "outcome_support": round(cs.outcome_support, 4),
                    "composite_score": round(cs.composite_score, 4),
                    "matching_history_count": cs.matching_history_count,
                    "eligible_measured_count": cs.eligible_measured_count,
                }
                for cs in res.candidate_scores
            ],
        }

    a_b_agree = res_a.selected_candidate_id == res_b.selected_candidate_id
    a_c_agree = res_a.selected_candidate_id == res_c.selected_candidate_id
    b_c_agree = res_b.selected_candidate_id == res_c.selected_candidate_id

    print(f"\n  Policy A -> {res_a.selected_candidate_id} (fallback={res_a.fallback_used})")
    print(f"  Policy B -> {res_b.selected_candidate_id} (fallback={res_b.fallback_used})")
    print(f"  Policy C -> {res_c.selected_candidate_id} (fallback={res_c.fallback_used})")
    print(f"\n  A==B: {a_b_agree} | A==C: {a_c_agree} | B==C: {b_c_agree}")

    selection_timestamp = datetime.now(timezone.utc).isoformat()

    selection_record = {
        "case_id": T9_CASE["case_id"],
        "template_id": T9_CASE["template_id"],
        "sql": sql,
        "canonical_template": t9_canonical,
        "template_hash": t9_actual_hash,
        "target_table": T9_CASE["target_table"],
        "eligible_count": len(eligible),
        "eligible_candidates": eligible,
        "candidate_evaluation_results": preflight_result["all_candidates"],
        "selections": {
            "policy_a": _fmt_sel(res_a),
            "policy_b": _fmt_sel(res_b),
            "policy_c": _fmt_sel(res_c),
        },
        "a_b_agree": a_b_agree,
        "a_c_agree": a_c_agree,
        "b_c_agree": b_c_agree,
        "hyperparameters": {
            "alpha": ALPHA,
            "beta": BETA,
            "lambda_reg": LAMBDA_REG,
        },
        "train_retrieval_ids": TRAIN_MEMORY_IDS,
        "phase6c_sha256": PHASE6C_SHA256,
        "phase8_manifest_path": "research/phase8_experiment_manifest.json",
        "selection_timestamp": selection_timestamp,
        "run_id": run_id,
    }

    sel_path = research_path / "phase8_selection_results.json"
    sel_path.write_text(json.dumps([selection_record], indent=2))
    print(f"\n  [LOCKED] Selections written BEFORE physical measurement: {sel_path}")
    print(f"  Selection timestamp: {selection_timestamp}")
    print(f"\n  *** POLICY SELECTIONS ARE NOW FROZEN. PHYSICAL MEASUREMENT BEGINS NEXT. ***")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4: PHYSICAL MEASUREMENT — ALL ELIGIBLE CANDIDATES INDEPENDENTLY
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: PHYSICAL MEASUREMENT (W=2, N=10, ALL ELIGIBLE CANDIDATES)")
    print("=" * 70)

    candidate_benchmarks = []

    for cand in eligible:
        key = cand["canonical_key"]
        cols = cand["columns"]
        cid_label = cand["candidate_id"]
        print(f"\n  Measuring: {key}")
        print(f"    candidate_id={cid_label}, is_baseline={cand['is_baseline']}")
        print(f"    Creating idx_autodba_p8_{T9_CASE['target_table']}_{('_'.join(c.lower() for c in cols))} ...",
              end="", flush=True)

        try:
            bm = benchmark_candidate(
                query=sql,
                table=T9_CASE["target_table"],
                columns=cols,
                candidate_label=key,
            )
            bm["candidate_id"] = cid_label
            bm["canonical_key"] = key
            bm["is_baseline"] = cand["is_baseline"]
            bm["hypopg_cost_improvement"] = cand["hypopg_cost_improvement"]

            print(f" DONE")
            print(f"    T_before={bm['t_before_ms']}ms | T_after={bm['t_after_ms']}ms "
                  f"| dT%={bm['runtime_improvement_percent']}%")
            print(f"    Scan before={bm['scan_type_before']} -> after={bm['scan_type_after']}")
            print(f"    CoV_before={bm['cov_before']} | CoV_after={bm['cov_after']}")
            print(f"    Cleanup: {'OK' if bm['cleanup_success'] else 'FAILED'}")

        except Exception as e:
            print(f" ERROR: {e}")
            bm = {
                "candidate_id": cid_label,
                "canonical_key": key,
                "is_baseline": cand["is_baseline"],
                "hypopg_cost_improvement": cand["hypopg_cost_improvement"],
                "error": str(e),
                "runtime_improvement_percent": None,
                "cleanup_success": False,
                "t_before_ms": None,
                "t_after_ms": None,
            }

        candidate_benchmarks.append(bm)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5: ORACLE DETERMINATION (AFTER ALL MEASUREMENTS)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 5: ORACLE DETERMINATION (POST-HOC, AFTER ALL MEASUREMENTS)")
    print("=" * 70)

    valid_bms = [b for b in candidate_benchmarks
                 if b.get("runtime_improvement_percent") is not None]

    if not valid_bms:
        oracle = None
        print("  [WARN] No valid benchmarks — oracle cannot be determined.")
    else:
        # Check for ties
        max_dt = max(b["runtime_improvement_percent"] for b in valid_bms)
        tied = [b for b in valid_bms if b["runtime_improvement_percent"] == max_dt]
        if len(tied) > 1:
            print(f"  [TIE] {len(tied)} candidates tied at {max_dt}%:")
            for t in tied:
                print(f"    {t['canonical_key']}: {t['runtime_improvement_percent']}%")
            # Break tie by lexicographic candidate_id (deterministic)
            best = min(tied, key=lambda b: b["candidate_id"])
            print(f"  Tie broken lexicographically -> {best['candidate_id']}")
        else:
            best = tied[0]

        oracle = {
            "candidate_id": best["candidate_id"],
            "canonical_key": best["canonical_key"],
            "columns": best["target_columns"],
            "runtime_improvement_percent": best["runtime_improvement_percent"],
            "t_after_ms": best.get("t_after_ms"),
            "is_tie": len(tied) > 1,
            "tied_candidates": [t["candidate_id"] for t in tied] if len(tied) > 1 else [],
        }
        print(f"  Oracle: {oracle['candidate_id']} | dT%={oracle['runtime_improvement_percent']}%")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 6: POLICY vs ORACLE COMPARISON
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 6: POLICY vs ORACLE COMPARISON")
    print("=" * 70)

    bm_by_cid = {b["candidate_id"]: b for b in candidate_benchmarks}
    oracle_dt = oracle["runtime_improvement_percent"] if oracle else None

    policy_evaluations = {}
    for pol_key, pol_res, pol_name in [
        ("policy_a", res_a, "Policy A"),
        ("policy_b", res_b, "Policy B"),
        ("policy_c", res_c, "Policy C"),
    ]:
        sel_cid = pol_res.selected_candidate_id
        matched = bm_by_cid.get(sel_cid)
        if matched and matched.get("runtime_improvement_percent") is not None:
            pol_dt = matched["runtime_improvement_percent"]
            pol_t_after = matched.get("t_after_ms")
            regret = max(0.0, round((oracle_dt - pol_dt), 2)) if oracle_dt is not None else None
            is_oracle = (oracle is not None and sel_cid == oracle["candidate_id"])
        else:
            pol_dt = None
            pol_t_after = None
            regret = None
            is_oracle = False

        policy_evaluations[pol_key] = {
            "selected_candidate_id": sel_cid,
            "runtime_improvement_percent": pol_dt,
            "oracle_improvement_percent": oracle_dt,
            "selection_regret_percent": regret,
            "is_oracle": is_oracle,
            "fallback_used": pol_res.fallback_used,
        }

        print(f"  {pol_name}: {sel_cid}")
        print(f"    dT%={pol_dt}% | oracle_dT%={oracle_dt}% | regret={regret}% | OA={is_oracle}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 7: MEMORY ISOLATION VERIFICATION
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 7: MEMORY ISOLATION VERIFICATION")
    print("=" * 70)

    with engine.connect() as conn:
        final_mem_count = conn.execute(
            text("SELECT COUNT(*) FROM optimization_memories")
        ).scalar()
        final_residual = count_autodba_indexes()
        final_mem_rows = conn.execute(
            text("SELECT id FROM optimization_memories ORDER BY id")
        ).fetchall()

    final_ids = [r[0] for r in final_mem_rows]
    mem_count_ok = final_mem_count == 14
    residual_ok = final_residual == 0
    ids_ok = sorted(final_ids) == list(range(1, 15))

    print(f"  optimization_memories count: {final_mem_count} (expected 14) — {'OK' if mem_count_ok else 'FAIL'}")
    print(f"  Memory IDs 1–14 intact: {ids_ok} — {'OK' if ids_ok else 'FAIL'}")
    print(f"  Residual idx_autodba_* indexes: {final_residual} (expected 0) — {'OK' if residual_ok else 'FAIL'}")

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 8: PERSIST MEASUREMENT ARTIFACTS
    # ─────────────────────────────────────────────────────────────────────────
    measurements = {
        "run_id": run_id,
        "created_at": run_timestamp,
        "phase": "8",
        "case_id": T9_CASE["case_id"],
        "template_id": T9_CASE["template_id"],
        "sql": sql,
        "canonical_template": t9_canonical,
        "template_hash": t9_actual_hash,
        "target_table": T9_CASE["target_table"],
        "phase6c_sha256": PHASE6C_SHA256,
        "phase6c_sha256_verified": True,
        "hyperparameters": {
            "alpha": ALPHA,
            "beta": BETA,
            "lambda_reg": LAMBDA_REG,
            "warmup_runs": WARMUP_RUNS,
            "measured_runs": MEASURED_RUNS,
        },
        "preflight": {
            "total_candidates_from_phase1": preflight_result["total_candidates_from_phase1"],
            "eligible_count": preflight_result["eligible_count"],
            "multi_candidate": preflight_result["multi_candidate"],
            "has_baseline": preflight_result["has_baseline"],
        },
        "candidate_benchmarks": candidate_benchmarks,
        "oracle": oracle,
        "policy_evaluations": policy_evaluations,
        "selection_timestamp": selection_timestamp,
        "post_run_memory_count": final_mem_count,
        "post_run_residual_indexes": final_residual,
        "memory_isolation_ok": mem_count_ok and residual_ok and ids_ok,
    }

    meas_path = research_path / "phase8_measurements.json"
    meas_path.write_text(json.dumps(measurements, indent=2))
    print(f"\n  Measurements written: {meas_path}")

    return measurements


if __name__ == "__main__":
    results = run_phase8()
    print("\n" + "=" * 70)
    print("Phase 8 execution complete.")
    print(f"Oracle: {results['oracle']}")
    pol_evals = results["policy_evaluations"]
    for pkey in ["policy_a", "policy_b", "policy_c"]:
        pe = pol_evals[pkey]
        print(f"  {pkey}: dT%={pe['runtime_improvement_percent']} "
              f"regret={pe['selection_regret_percent']} OA={pe['is_oracle']}")
