"""
Phase 7: Targeted Measured-Corpus Execution
============================================
Executes the full A/B/C comparative experiment for Phase 7 proposed cases.

Strict invariants (identical to Phase 6D):
  1. Preflight: Actual Phase 1 candidate generation via IntelligenceService.
  2. Canonicalization: TP-A vs TP-D distinctness verified.
  3. Offline policy selection locked BEFORE any physical measurement.
  4. Physical benchmarking uses established W=2, N=10 protocol.
  5. Zero optimization_memories mutations.
  6. TRAIN retrieval strictly limited to Memory IDs 1-6.
  7. Phase 7 outcomes stored in research artifacts only.
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
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TRAIN_MEMORY_IDS = [1, 2, 3, 4, 5, 6]
PHASE6C_SHA256 = "b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27"
WARMUP_RUNS = 2
MEASURED_RUNS = 10
ALPHA = 1.0
BETA = 1.0
LAMBDA_REG = 1.5

PROPOSED_CASES = [
    # PREFLIGHT CORRECTIONS (2):
    # 1. Status values are lowercase in the database ('pending' not 'PENDING').
    # 2. Parameters updated to total_amount > 440+ range to trigger HypoPG index
    #    use — confirmed by manual HypoPG testing with both hypothetical indexes.
    #    Lower thresholds (> 150-350) return too many rows; planner prefers Seq Scan.
    #    Values chosen are distinct from existing TRAIN values (> 420, > 450, > 480).
    {"case_id": "CASE-TP-A-01", "template_id": "TP-A",
     "sql": "SELECT * FROM orders WHERE total_amount > 455.00 AND status = 'pending'",
     "target_table": "orders"},
    {"case_id": "CASE-TP-A-02", "template_id": "TP-A",
     "sql": "SELECT * FROM orders WHERE total_amount > 460.00 AND status = 'shipped'",
     "target_table": "orders"},
    {"case_id": "CASE-TP-A-03", "template_id": "TP-A",
     "sql": "SELECT * FROM orders WHERE total_amount > 443.00 AND status = 'completed'",
     "target_table": "orders"},
    {"case_id": "CASE-TP-D-01", "template_id": "TP-D",
     "sql": "SELECT * FROM orders WHERE status = 'cancelled' AND total_amount > 455.00",
     "target_table": "orders"},
    {"case_id": "CASE-TP-D-02", "template_id": "TP-D",
     "sql": "SELECT * FROM orders WHERE status = 'processing' AND total_amount > 445.00",
     "target_table": "orders"},
    {"case_id": "CASE-TP-B-01", "template_id": "TP-B",
     "sql": "SELECT * FROM orders WHERE order_date >= '2025-02-15' AND total_amount > 455.00",
     "target_table": "orders"},
]


class _DetProvider(LLMProvider):
    def explain(self, *, query, diagnosis, recommendation, similar_cases):
        return "Deterministic research run."


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def count_autodba_indexes() -> int:
    with engine.connect() as conn:
        return int(conn.execute(
            text("SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%'")
        ).scalar() or 0)


def load_train_cases() -> List[OptimizationCase]:
    """Load strictly TRAIN cases (Memory IDs 1-6) from optimization_memories."""
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
    warmup_runs: int = WARMUP_RUNS,
    measured_runs: int = MEASURED_RUNS,
) -> Dict[str, Any]:
    """
    Physically benchmarks a candidate index in isolation.
    Protocol identical to Phase 6D benchmark_single_candidate.
    """
    # Pre-flight zero-index check
    pre_residual = count_autodba_indexes()
    if pre_residual > 0:
        raise ResearchSafetyError(
            f"Pre-flight failed: {pre_residual} residual idx_autodba_* indexes present!"
        )

    clean_cols = [c.strip().lower() for c in columns if c and c.strip()]
    col_str = "_".join(clean_cols)
    idx_name = f"idx_autodba_p7_{table.lower()}_{col_str}"
    cols_ddl = ", ".join(clean_cols)

    db = SessionLocal()
    try:
        # === Step A: Baseline measurement (disable index scans) ===
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

        # Verify index creation
        with engine.connect() as chk:
            idx_exists = chk.execute(
                text("SELECT COUNT(*) FROM pg_indexes WHERE indexname = :n"),
                {"n": idx_name},
            ).scalar()
            if not idx_exists:
                raise RuntimeError(f"Index {idx_name} creation failed.")

        # === Step C: Post-index measurement (enable index scans) ===
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
        "t_before_ms": round(mean_before, 4),
        "t_after_ms": round(mean_after, 4),
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

def run_phase7():
    print("=" * 80)
    print("PHASE 7: TARGETED MEASURED-CORPUS EXECUTION")
    print("=" * 80)
    run_timestamp = datetime.now(timezone.utc).isoformat()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ─────────────────────────────────────────────────────────────────────────
    # 0. Verify Phase 6C partition still locked
    # ─────────────────────────────────────────────────────────────────────────
    p6c_path = research_path / "phase6c_partition_manifest.json"
    actual_sha = hashlib.sha256(p6c_path.read_bytes()).hexdigest()
    if actual_sha != PHASE6C_SHA256:
        raise RuntimeError(f"Phase 6C manifest hash mismatch! Expected {PHASE6C_SHA256}, got {actual_sha}")
    print(f"[OK] Phase 6C partition locked (SHA-256: {actual_sha[:20]}...)")

    # Verify zero residual indexes at start
    start_residual = count_autodba_indexes()
    if start_residual != 0:
        raise ResearchSafetyError(f"Start-of-run residual idx_autodba_* count: {start_residual}. Aborting.")
    print(f"[OK] Zero residual idx_autodba_* indexes at start.")

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PREFLIGHT: Actual Phase 1 candidate generation
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 1: EXECUTION PREFLIGHT (Actual Phase 1 Candidate Generation)")
    print("=" * 70)

    # Canonicalization collision check
    print("\n--- TP-A vs TP-D canonicalization check ---")
    canon_results = {}
    seen_hashes: Dict[str, str] = {}
    hash_collisions = []
    for case in PROPOSED_CASES:
        cid = case["case_id"]
        canon = canonicalize_sql(case["sql"])
        h = compute_template_hash(case["sql"])
        canon_results[cid] = {"canonical": canon, "hash": h}
        if h in seen_hashes:
            hash_collisions.append((cid, seen_hashes[h], h, canon))
            print(f"  !! COLLISION: {cid} == {seen_hashes[h]}")
            print(f"     Both canonical: {canon}")
        else:
            seen_hashes[h] = cid
            print(f"  {cid} ({case['template_id']}): {canon}")
            print(f"    hash: {h[:20]}...")

    if hash_collisions:
        print(f"\n  FINDING: {len(hash_collisions)} canonicalization collision(s) detected.")
        print("  Consequence: Colliding cases share the same template. Will be")
        print("  treated as the same template in the partition, but counted as")
        print("  distinct cases for execution purposes.")
    else:
        print("\n  [OK] All 6 proposed cases have distinct canonical templates.")

    # Run Phase 1 diagnose for each case
    llm = LLMService(provider=_DetProvider())
    preflight_results: Dict[str, Any] = {}

    with SessionLocal() as db:
        intel = IntelligenceService(db, llm_service=llm)

        for case in PROPOSED_CASES:
            cid = case["case_id"]
            sql = case["sql"]
            print(f"\n  [{cid}] {sql[:70]}")

            db.rollback()
            try:
                diag = intel.diagnose(
                    request=DiagnoseRequest(
                        query=sql,
                        incident_type="missing_index",
                        include_rag=False,
                    )
                )
            except Exception as e:
                print(f"    ERROR: {e}")
                preflight_results[cid] = {
                    "error": str(e), "eligible_candidates": [],
                    "preflight_pass": False, "total_candidates": 0,
                }
                continue

            candidates = diag.diagnosis.candidate_evaluations or []
            print(f"    Phase 1 generated {len(candidates)} candidate(s):")

            eligible = []
            all_candidates = []

            for ce in candidates:
                rec = ce.recommendation
                sa = ce.safety_assessment
                cols = list(rec.columns or [])
                table_name = (rec.relation or "").lower()
                key = f"{table_name}:btree:{','.join(c.lower() for c in cols)}"

                # Determine HypoPG verdict
                hypo_verdict = "N/A"
                hypo_pct = None
                if ce.validation:
                    v = ce.validation.verdict
                    # ValidationVerdict enum values are lowercase ('validated', not 'VALIDATED')
                    hypo_verdict = v.value if hasattr(v, "value") else str(v)
                    if ce.validation.comparison:
                        hypo_pct = ce.validation.comparison.cost_improvement_percent

                # Compare against lowercase enum value
                hypo_ok = hypo_verdict == "validated"
                safety_ok = bool(sa and sa.eligible_for_approval)

                blocking = []
                if sa and sa.blocking_reasons:
                    blocking = list(sa.blocking_reasons)

                pct_str = f"{hypo_pct:.1f}%" if hypo_pct is not None else "N/A"
                status_tag = "ELIGIBLE" if (hypo_ok and safety_ok) else "EXCLUDED"
                print(f"    {status_tag}: {key} | baseline={ce.is_baseline} | "
                      f"HypoPG={hypo_verdict}({pct_str}) | safety={safety_ok}"
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
                    # Attributes needed by CandidateSelector
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

            multi_cand = len(eligible) >= 2
            has_baseline = any(c["is_baseline"] for c in eligible)
            print(f"    Eligible: {len(eligible)} | multi-candidate: {multi_cand} | has_baseline: {has_baseline}")

            preflight_results[cid] = {
                "case_id": cid,
                "template_id": case["template_id"],
                "sql": sql,
                "canonical_template": canon_results[cid]["canonical"],
                "template_hash": canon_results[cid]["hash"],
                "target_table": case["target_table"],
                "total_candidates": len(candidates),
                "all_candidates": all_candidates,
                "eligible_candidates": eligible,
                "eligible_count": len(eligible),
                "multi_candidate": multi_cand,
                "has_baseline": has_baseline,
                # Pass: ≥1 eligible AND has exactly one baseline
                "preflight_pass": len(eligible) >= 1 and has_baseline,
            }

    active = [c for c in PROPOSED_CASES if preflight_results.get(c["case_id"], {}).get("preflight_pass")]
    blocked = [c for c in PROPOSED_CASES if not preflight_results.get(c["case_id"], {}).get("preflight_pass")]

    print(f"\nPREFLIGHT SUMMARY: {len(active)} pass / {len(blocked)} blocked")
    for bc in blocked:
        pf = preflight_results.get(bc["case_id"], {})
        reason = pf.get("error") or (
            "no_eligible_candidates" if pf.get("eligible_count", 0) == 0 else
            "no_baseline_in_eligible_pool"
        )
        print(f"  BLOCKED: {bc['case_id']} — {reason}")

    if not active:
        print("\nAll cases blocked. Stopping Phase 7.")
        return

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LOCK EXPERIMENT MANIFEST
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 2: LOCKING EXPERIMENT MANIFEST")
    print("=" * 70)

    design_manifest_path = research_path / "phase7_corpus_design_manifest.json"
    design_manifest_hash = hashlib.sha256(design_manifest_path.read_bytes()).hexdigest()

    experiment_manifest = {
        "run_id": run_id,
        "created_at": run_timestamp,
        "phase": "7",
        "status": "LOCKED",
        "phase6c_sha256": PHASE6C_SHA256,
        "phase6c_sha256_verified": True,
        "design_manifest_sha256": design_manifest_hash,
        "frozen_train_retrieval_ids": TRAIN_MEMORY_IDS,
        "hyperparameters": {
            "alpha": ALPHA,
            "beta": BETA,
            "lambda_reg": LAMBDA_REG,
            "warmup_runs": WARMUP_RUNS,
            "measured_runs": MEASURED_RUNS,
        },
        "canonicalization_collisions": hash_collisions,
        "cases": {
            cid: {
                "case_id": cid,
                "template_id": preflight_results[cid]["template_id"],
                "sql": preflight_results[cid]["sql"],
                "canonical_template": preflight_results[cid]["canonical_template"],
                "template_hash": preflight_results[cid]["template_hash"],
                "target_table": preflight_results[cid]["target_table"],
                "eligible_candidates": preflight_results[cid]["eligible_candidates"],
                "eligible_count": preflight_results[cid]["eligible_count"],
                "multi_candidate": preflight_results[cid]["multi_candidate"],
                "preflight_pass": preflight_results[cid]["preflight_pass"],
            }
            for cid in [c["case_id"] for c in PROPOSED_CASES]
        },
        "active_case_ids": [c["case_id"] for c in active],
        "blocked_case_ids": [c["case_id"] for c in blocked],
    }

    manifest_path = research_path / "phase7_experiment_manifest.json"
    manifest_path.write_text(json.dumps(experiment_manifest, indent=2))
    print(f"  Experiment manifest locked: {manifest_path}")
    print(f"  Active cases: {experiment_manifest['active_case_ids']}")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. OFFLINE POLICY SELECTION (before physical measurement)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3: OFFLINE POLICY SELECTION (LOCKED BEFORE PHYSICAL MEASUREMENT)")
    print("=" * 70)

    train_cases = load_train_cases()
    print(f"  TRAIN cases loaded: {len(train_cases)} (IDs {TRAIN_MEMORY_IDS})")

    selector = CandidateSelector(alpha=ALPHA, beta=BETA, lambda_reg=LAMBDA_REG)
    selection_results: List[Dict[str, Any]] = []

    for case_data in PROPOSED_CASES:
        cid = case_data["case_id"]
        pf = preflight_results[cid]

        if not pf["preflight_pass"]:
            print(f"\n  [{cid}] SKIPPED (preflight failed)")
            selection_results.append({"case_id": cid, "skipped": True,
                                      "reason": "preflight_failed"})
            continue

        eligible = pf["eligible_candidates"]
        sql = case_data["sql"]
        print(f"\n  [{cid}] Pool: {[e['canonical_key'] for e in eligible]}")

        res_a = selector.select_planner_only(eligible)
        res_b = selector.select_similarity(sql, eligible, train_cases)
        res_c = selector.select_outcome_aware(sql, eligible, train_cases)

        def _fmt(res):
            return {
                "selected_candidate_id": res.selected_candidate_id,
                "fallback_used": res.fallback_used,
                "fallback_reason": res.fallback_reason,
                "historical_support_count": res.historical_support.get("total_matching_cases", 0)
                    if res.historical_support else 0,
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

        print(f"    Policy A: {res_a.selected_candidate_id} (fallback={res_a.fallback_used})")
        print(f"    Policy B: {res_b.selected_candidate_id} (fallback={res_b.fallback_used})")
        print(f"    Policy C: {res_c.selected_candidate_id} (fallback={res_c.fallback_used})")

        a_b_agree = res_a.selected_candidate_id == res_b.selected_candidate_id
        a_c_agree = res_a.selected_candidate_id == res_c.selected_candidate_id
        print(f"    A==B: {a_b_agree} | A==C: {a_c_agree}")

        selection_results.append({
            "case_id": cid,
            "template_id": case_data["template_id"],
            "sql": sql,
            "target_table": case_data["target_table"],
            "eligible_count": len(eligible),
            "eligible_candidates": [e["canonical_key"] for e in eligible],
            "selections": {
                "policy_a": _fmt(res_a),
                "policy_b": _fmt(res_b),
                "policy_c": _fmt(res_c),
            },
            "a_b_agree": a_b_agree,
            "a_c_agree": a_c_agree,
            "b_c_agree": res_b.selected_candidate_id == res_c.selected_candidate_id,
            "skipped": False,
        })

    # Persist selection results BEFORE any physical measurement
    sel_path = research_path / "phase7_selection_results.json"
    sel_path.write_text(json.dumps(selection_results, indent=2))
    print(f"\n  [LOCKED] Selection results persisted BEFORE physical measurement: {sel_path}")

    # ─────────────────────────────────────────────────────────────────────────
    # 4. PHYSICAL MEASUREMENT (W=2, N=10)
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: PHYSICAL MEASUREMENT (W=2, N=10)")
    print("=" * 70)

    measurement_records: List[Dict[str, Any]] = []

    for case_data in PROPOSED_CASES:
        cid = case_data["case_id"]
        pf = preflight_results[cid]

        if not pf["preflight_pass"]:
            print(f"\n  [{cid}] SKIPPED")
            measurement_records.append({
                "case_id": cid, "skipped": True,
                "reason": "preflight_failed", "oracle": None,
            })
            continue

        sql = case_data["sql"]
        table = case_data["target_table"]
        eligible = pf["eligible_candidates"]
        print(f"\n  [{cid}] Benchmarking {len(eligible)} candidate(s):")

        candidate_benchmarks = []
        for cand in eligible:
            key = cand["canonical_key"]
            cols = cand["columns"]
            print(f"    Candidate: {key} ...", end="", flush=True)
            try:
                bm = benchmark_candidate(sql, table, cols)
                bm["candidate_id"] = cand["candidate_id"]
                bm["canonical_key"] = key
                bm["is_baseline"] = cand["is_baseline"]
                bm["hypopg_cost_improvement"] = cand["hypopg_cost_improvement"]
                delta = bm.get("runtime_improvement_percent")
                print(f" dT={delta}% | before={bm['t_before_ms']}ms | "
                      f"after={bm['t_after_ms']}ms | cleanup={bm['cleanup_success']}")
            except Exception as e:
                print(f" ERROR: {e}")
                bm = {
                    "candidate_id": cand["candidate_id"],
                    "canonical_key": key,
                    "is_baseline": cand["is_baseline"],
                    "error": str(e),
                    "runtime_improvement_percent": None,
                    "cleanup_success": False,
                }
            candidate_benchmarks.append(bm)

        # Oracle: candidate with max measured ΔT%
        valid = [b for b in candidate_benchmarks
                 if b.get("runtime_improvement_percent") is not None]
        oracle = None
        if valid:
            best = max(valid, key=lambda b: b["runtime_improvement_percent"])
            oracle = {
                "candidate_id": best["candidate_id"],
                "canonical_key": best["canonical_key"],
                "columns": best["target_columns"],
                "runtime_improvement_percent": best["runtime_improvement_percent"],
                "t_after_ms": best.get("t_after_ms"),
            }
            print(f"    Oracle: {oracle['candidate_id']} ({oracle['runtime_improvement_percent']}%)")

        measurement_records.append({
            "case_id": cid,
            "template_id": case_data["template_id"],
            "query_text": sql,
            "target_table": table,
            "candidate_count": len(eligible),
            "candidate_benchmarks": candidate_benchmarks,
            "oracle": oracle,
            "skipped": False,
        })

    meas_path = research_path / "phase7_measurements.json"
    meas_path.write_text(json.dumps(measurement_records, indent=2))
    print(f"\n  Measurements persisted: {meas_path}")

    # ─────────────────────────────────────────────────────────────────────────
    # 5. MEMORY ISOLATION VERIFICATION
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 5: MEMORY ISOLATION VERIFICATION")
    print("=" * 70)

    with engine.connect() as conn:
        mem_count = conn.execute(
            text("SELECT COUNT(*) FROM optimization_memories")
        ).scalar()
        residual = count_autodba_indexes()
        mem_rows = conn.execute(
            text("SELECT id, provenance, is_verified, verification_state "
                 "FROM optimization_memories ORDER BY id")
        ).fetchall()

    print(f"  optimization_memories count: {mem_count} (expected: 14)")
    print(f"  Residual idx_autodba_* indexes: {residual} (expected: 0)")
    print(f"  Memory IDs present: {[r[0] for r in mem_rows]}")

    mem_ok = mem_count == 14
    residual_ok = residual == 0
    all_ids_ok = sorted([r[0] for r in mem_rows]) == list(range(1, 15))

    for r in mem_rows:
        ok = r[1] == "measured" and r[2] and r[3] == "verified_measured"
        if not ok:
            print(f"  WARNING: ID {r[0]} state anomaly: {r}")

    print(f"\n  Memory count OK: {mem_ok}")
    print(f"  Residual indexes OK: {residual_ok}")
    print(f"  Memory IDs 1-14 intact: {all_ids_ok}")

    # ─────────────────────────────────────────────────────────────────────────
    # 6. OUTPUT SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 6: OUTPUT SUMMARY")
    print("=" * 70)

    active_selections = [s for s in selection_results if not s.get("skipped")]
    active_measurements = [m for m in measurement_records if not m.get("skipped")]

    print(f"\n  Cases active:  {len(active)}")
    print(f"  Cases blocked: {len(blocked)}")
    print(f"  Selections recorded: {len(active_selections)}")
    print(f"  Measurement records: {len(active_measurements)}")

    # Agreement analysis
    disagreements_ab = sum(1 for s in active_selections if not s.get("a_b_agree"))
    disagreements_ac = sum(1 for s in active_selections if not s.get("a_c_agree"))
    fallbacks_b = sum(
        1 for s in active_selections
        if s.get("selections", {}).get("policy_b", {}).get("fallback_used")
    )
    fallbacks_c = sum(
        1 for s in active_selections
        if s.get("selections", {}).get("policy_c", {}).get("fallback_used")
    )
    print(f"\n  A!=B disagreements: {disagreements_ab}/{len(active_selections)}")
    print(f"  A!=C disagreements: {disagreements_ac}/{len(active_selections)}")
    print(f"  Policy B fallbacks: {fallbacks_b}/{len(active_selections)}")
    print(f"  Policy C fallbacks: {fallbacks_c}/{len(active_selections)}")

    # Oracle agreement
    sel_by_cid = {s["case_id"]: s for s in active_selections}
    meas_by_cid = {m["case_id"]: m for m in active_measurements}
    oracle_agreement = {"A": 0, "B": 0, "C": 0}
    evaluated = 0
    for cid, sel in sel_by_cid.items():
        meas = meas_by_cid.get(cid)
        if not meas or not meas.get("oracle"):
            continue
        evaluated += 1
        oracle_id = meas["oracle"]["candidate_id"]
        for pol, key in [("A", "policy_a"), ("B", "policy_b"), ("C", "policy_c")]:
            if sel["selections"][key]["selected_candidate_id"] == oracle_id:
                oracle_agreement[pol] += 1

    print(f"\n  Oracle agreement (out of {evaluated} evaluable cases):")
    for pol in ["A", "B", "C"]:
        print(f"    Policy {pol}: {oracle_agreement[pol]}/{evaluated}")

    print(f"\n  Artifacts:")
    print(f"    research/phase7_experiment_manifest.json")
    print(f"    research/phase7_selection_results.json")
    print(f"    research/phase7_measurements.json")

    return {
        "preflight": preflight_results,
        "selection_results": selection_results,
        "measurement_records": measurement_records,
        "active_count": len(active),
        "blocked_count": len(blocked),
        "memory_ok": mem_ok and residual_ok and all_ids_ok,
        "oracle_agreement": oracle_agreement,
        "disagreements_ab": disagreements_ab,
        "disagreements_ac": disagreements_ac,
        "fallbacks_b": fallbacks_b,
        "fallbacks_c": fallbacks_c,
        "evaluated_for_oracle": evaluated,
    }


if __name__ == "__main__":
    results = run_phase7()
    print("\n" + "=" * 70)
    print("Phase 7 execution complete.")
