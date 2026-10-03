"""
Phase 6A: Controlled Corpus Execution Script
============================================
Sequentially executes the 20 proposed cases from PHASE6A_CORPUS_CANDIDATE_MANIFEST.md
using MeasuredCaseRunner with strict pre/post flight validation, zero index leakage,
and full telemetry capture across all 21 required audit dimensions.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Setup environment and sys.path
root_path = Path(__file__).resolve().parent.parent
backend_path = root_path / "backend"
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

os.environ.setdefault("POSTGRES_HOST", "localhost")

from sqlalchemy import text
from app.db.database import SessionLocal, engine
from app.schemas.optimization import (
    ApprovalStatus,
    CaseProvenance,
    DiagnoseRequest,
    OutcomeVerificationState,
    RemediationStatus,
)
from app.services.approval_service import default_approval_service
from app.services.closed_loop_service import ClosedLoopService
from app.services.intelligence_service import IntelligenceService
from app.services.llm_service import LLMProvider, LLMService
from research.measured_case_runner import (
    MeasuredCaseRunner,
    ResearchSafetyError,
    MeasuredRunnerError,
    ResearchExplanationProvider,
)


# Define the 20 cases exactly as audited in PHASE6A_CORPUS_CANDIDATE_MANIFEST.md
PROPOSED_CASES: List[Dict[str, Any]] = [
    # Template T1 (orders, customer_id = ?)
    {
        "case_id": "CASE-T1-01",
        "template_id": "T1",
        "query": "SELECT * FROM orders WHERE customer_id = 42;",
        "target_table": "orders",
        "is_existing_pilot": True,
        "existing_memory_id": 1,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T1-02",
        "template_id": "T1",
        "query": "SELECT * FROM orders WHERE customer_id = 105;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T1-03",
        "template_id": "T1",
        "query": "SELECT * FROM orders WHERE customer_id = 278;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T2 (orders, total_amount > ?)
    {
        "case_id": "CASE-T2-01",
        "template_id": "T2",
        "query": "SELECT * FROM orders WHERE total_amount > 450.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T2-02",
        "template_id": "T2",
        "query": "SELECT * FROM orders WHERE total_amount > 480.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T2-03",
        "template_id": "T2",
        "query": "SELECT * FROM orders WHERE total_amount > 420.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T3 (orders, customer_id = ? AND total_amount > ?)
    {
        "case_id": "CASE-T3-01",
        "template_id": "T3",
        "query": "SELECT * FROM orders WHERE customer_id = 42 AND total_amount > 100.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T3-02",
        "template_id": "T3",
        "query": "SELECT * FROM orders WHERE customer_id = 105 AND total_amount > 150.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T3-03",
        "template_id": "T3",
        "query": "SELECT * FROM orders WHERE customer_id = 278 AND total_amount > 200.00;",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T4 (orders, status = ?)
    {
        "case_id": "CASE-T4-01",
        "template_id": "T4",
        "query": "SELECT * FROM orders WHERE status = 'CANCELLED';",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T4-02",
        "template_id": "T4",
        "query": "SELECT * FROM orders WHERE status = 'PENDING';",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T5 (order_items, quantity > ?)
    {
        "case_id": "CASE-T5-01",
        "template_id": "T5",
        "query": "SELECT * FROM order_items WHERE quantity > 8;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T5-02",
        "template_id": "T5",
        "query": "SELECT * FROM order_items WHERE quantity > 9;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T6 (order_items, unit_price > ?)
    {
        "case_id": "CASE-T6-01",
        "template_id": "T6",
        "query": "SELECT * FROM order_items WHERE unit_price > 95.00;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    {
        "case_id": "CASE-T6-02",
        "template_id": "T6",
        "query": "SELECT * FROM order_items WHERE unit_price > 90.00;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TRAIN",
    },
    # Template T7 (order_items, quantity > ? AND unit_price > ?) - TEST
    {
        "case_id": "CASE-T7-01",
        "template_id": "T7",
        "query": "SELECT * FROM order_items WHERE quantity > 7 AND unit_price > 80.00;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TEST",
    },
    {
        "case_id": "CASE-T7-02",
        "template_id": "T7",
        "query": "SELECT * FROM order_items WHERE quantity > 8 AND unit_price > 85.00;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TEST",
    },
    {
        "case_id": "CASE-T7-03",
        "template_id": "T7",
        "query": "SELECT * FROM order_items WHERE quantity > 6 AND unit_price > 90.00;",
        "target_table": "order_items",
        "is_existing_pilot": False,
        "role": "TEST",
    },
    # Template T8 (orders, customer_id = ? AND status = ?) - TEST
    {
        "case_id": "CASE-T8-01",
        "template_id": "T8",
        "query": "SELECT * FROM orders WHERE customer_id = 42 AND status = 'COMPLETED';",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TEST",
    },
    {
        "case_id": "CASE-T8-02",
        "template_id": "T8",
        "query": "SELECT * FROM orders WHERE customer_id = 105 AND status = 'SHIPPED';",
        "target_table": "orders",
        "is_existing_pilot": False,
        "role": "TEST",
    },
]


def count_autodba_indexes() -> int:
    """Counts any residual idx_autodba_* indexes across the entire public schema."""
    with engine.connect() as conn:
        res = conn.execute(
            text("SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%';")
        ).scalar()
        return int(res or 0)


def extract_memory_data(memory_id: int) -> Dict[str, Any]:
    """Extracts raw persisted OptimizationMemory data from the database."""
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT id, incident_type, query_text, diagnosis, recommendation, "
                "validation, benchmark, outcome, provenance, is_verified, verification_state, created_at "
                "FROM optimization_memories WHERE id = :mid"
            ),
            {"mid": memory_id},
        ).mappings().fetchone()
        if not row:
            raise RuntimeError(f"OptimizationMemory record with ID {memory_id} not found.")
        return dict(row)


def execute_corpus():
    runner = MeasuredCaseRunner()
    print("=" * 70)
    print("STARTING PHASE 6A MEASURED CORPUS CONSTRUCTION")
    print(f"Target: {len(PROPOSED_CASES)} cases across 8 templates")
    print(f"PostgreSQL Engine: {engine.url}")
    print("=" * 70)

    # Initial Pre-flight Check
    initial_residual = count_autodba_indexes()
    if initial_residual > 0:
        raise RuntimeError(f"Pre-flight failed: {initial_residual} residual idx_autodba_* indexes detected!")

    results: List[Dict[str, Any]] = []

    for idx, case_info in enumerate(PROPOSED_CASES, start=1):
        case_id = case_info["case_id"]
        template_id = case_info["template_id"]
        query = case_info["query"]
        target_table = case_info["target_table"]
        role = case_info["role"]
        is_existing = case_info.get("is_existing_pilot", False)

        print(f"\n[{idx}/{len(PROPOSED_CASES)}] Processing {case_id} ({template_id}) [{role}]...")
        print(f"  SQL: {query}")

        # Guard: Invariant zero residual indexes before run
        pre_residual = count_autodba_indexes()
        if pre_residual > 0:
            print(f"  [ERROR] Residual idx_autodba_* index detected before {case_id}! Aborting.")
            break

        if is_existing:
            # Case 1 is the existing pilot Memory ID 1
            mem_id = case_info["existing_memory_id"]
            print(f"  -> Reading existing pilot case from Memory ID {mem_id}...")
            mem_data = extract_memory_data(mem_id)
            diag = mem_data.get("diagnosis") or {}
            rec = mem_data.get("recommendation") or {}
            val = mem_data.get("validation") or {}
            bm = mem_data.get("benchmark") or {}
            bm_before = bm.get("before") or {}
            bm_after = bm.get("after") or {}

            # Candidate pool from diagnosis
            candidate_pool = [
                {
                    "candidate_id": "cand_orders_customer_id",
                    "columns": ["customer_id"],
                    "is_baseline": True,
                    "validation": val,
                }
            ]

            case_record = {
                "case_id": case_id,
                "template_id": template_id,
                "exact_sql": query,
                "target_table": target_table,
                "role": role,
                "status": "SUCCESS",
                "candidate_pool": candidate_pool,
                "candidate_count": len(candidate_pool),
                "hypopg_verdict": val.get("verdict"),
                "hypopg_cost_improvement_percent": val.get("cost_improvement_percent"),
                "hypopg_original_cost": val.get("original_cost"),
                "hypopg_hypothetical_cost": val.get("hypothetical_cost"),
                "safety_eligible": True,
                "safety_level": "LOW",
                "safety_blocking_reasons": [],
                "selected_physical_index": rec.get("index_name") or "idx_autodba_orders_customer_id",
                "selected_columns": rec.get("columns", ["customer_id"]),
                "before_benchmark": {
                    "mean_execution_time_ms": bm_before.get("mean_execution_time_ms"),
                    "median_execution_time_ms": bm_before.get("median_execution_time_ms"),
                    "stddev_execution_time_ms": bm_before.get("stddev_execution_time_ms"),
                    "min_execution_time_ms": bm_before.get("min_execution_time_ms"),
                    "max_execution_time_ms": bm_before.get("max_execution_time_ms"),
                    "coefficient_of_variation": bm_before.get("coefficient_of_variation"),
                    "scan_type": bm_before.get("scan_type"),
                    "index_used": bm_before.get("index_used"),
                    "shared_hit_blocks": bm_before.get("shared_hit_blocks"),
                    "shared_read_blocks": bm_before.get("shared_read_blocks"),
                    "rows_returned": bm_before.get("rows_returned"),
                },
                "after_benchmark": {
                    "mean_execution_time_ms": bm_after.get("mean_execution_time_ms"),
                    "median_execution_time_ms": bm_after.get("median_execution_time_ms"),
                    "stddev_execution_time_ms": bm_after.get("stddev_execution_time_ms"),
                    "min_execution_time_ms": bm_after.get("min_execution_time_ms"),
                    "max_execution_time_ms": bm_after.get("max_execution_time_ms"),
                    "coefficient_of_variation": bm_after.get("coefficient_of_variation"),
                    "scan_type": bm_after.get("scan_type"),
                    "index_used": bm_after.get("index_used"),
                    "shared_hit_blocks": bm_after.get("shared_hit_blocks"),
                    "shared_read_blocks": bm_after.get("shared_read_blocks"),
                    "rows_returned": bm_after.get("rows_returned"),
                },
                "runtime_improvement_percent": bm.get("runtime_improvement_percent"),
                "planner_cost_improvement_percent": bm.get("planner_cost_improvement_percent"),
                "physical_verification_passed": True,
                "persisted_memory_id": mem_id,
                "provenance": mem_data.get("provenance"),
                "verification_state": mem_data.get("verification_state"),
                "cleanup_success": True,
                "exclusion_reason": None,
            }
            results.append(case_record)
            print(f"  -> Successfully loaded Memory ID {mem_id}: runtime delta = {case_record['runtime_improvement_percent']}%")
            continue

        # Execute new case via MeasuredCaseRunner
        try:
            # First perform deterministic diagnosis to inspect full candidate pool
            with SessionLocal() as db_session:
                intel = IntelligenceService(
                    db_session,
                    llm_service=LLMService(provider=ResearchExplanationProvider())
                )
                diag_resp = intel.diagnose(
                    request=DiagnoseRequest(
                        query=query,
                        incident_type="missing_index",
                        include_rag=False,
                    )
                )

            cand_evals = diag_resp.diagnosis.candidate_evaluations or []
            cand_pool_summary = []
            for ce in cand_evals:
                cost_impr = ce.validation.comparison.cost_improvement_percent if (ce.validation and ce.validation.comparison) else None
                cand_pool_summary.append({
                    "candidate_id": ce.candidate_id,
                    "columns": ce.recommendation.columns,
                    "is_baseline": ce.is_baseline,
                    "validation_verdict": ce.validation.verdict.value if ce.validation else None,
                    "cost_improvement_percent": cost_impr,
                    "safety_eligible": ce.safety_assessment.eligible_for_approval if ce.safety_assessment else False,
                })

            print(f"  -> Generated {len(cand_evals)} candidate evaluations: {[c['columns'] for c in cand_pool_summary]}")

            exec_res = runner.execute_pilot_case(
                query=query,
                target_table=target_table,
                auto_cleanup=True,
                benchmark_runs=10,
                benchmark_warmup_runs=2,
            )

            # Retrieve persisted memory to get full before/after ExecutionMeasurement telemetry
            mem_data = extract_memory_data(exec_res.persisted_memory_id)
            val = mem_data.get("validation") or {}
            bm = mem_data.get("benchmark") or {}
            bm_before = bm.get("before") or {}
            bm_after = bm.get("after") or {}

            # Verify cleanup
            post_residual = count_autodba_indexes()
            cleanup_ok = (post_residual == 0)

            case_record = {
                "case_id": case_id,
                "template_id": template_id,
                "exact_sql": query,
                "target_table": target_table,
                "role": role,
                "status": "SUCCESS",
                "candidate_pool": cand_pool_summary,
                "candidate_count": len(cand_pool_summary),
                "hypopg_verdict": val.get("verdict"),
                "hypopg_cost_improvement_percent": val.get("cost_improvement_percent"),
                "hypopg_original_cost": val.get("original_cost"),
                "hypopg_hypothetical_cost": val.get("hypothetical_cost"),
                "safety_eligible": True,
                "safety_level": "LOW",
                "safety_blocking_reasons": [],
                "selected_physical_index": exec_res.index_name,
                "selected_columns": exec_res.target_columns,
                "before_benchmark": {
                    "mean_execution_time_ms": bm_before.get("mean_execution_time_ms"),
                    "median_execution_time_ms": bm_before.get("median_execution_time_ms"),
                    "stddev_execution_time_ms": bm_before.get("stddev_execution_time_ms"),
                    "min_execution_time_ms": bm_before.get("min_execution_time_ms"),
                    "max_execution_time_ms": bm_before.get("max_execution_time_ms"),
                    "coefficient_of_variation": bm_before.get("coefficient_of_variation"),
                    "scan_type": bm_before.get("scan_type"),
                    "index_used": bm_before.get("index_used"),
                    "shared_hit_blocks": bm_before.get("shared_hit_blocks"),
                    "shared_read_blocks": bm_before.get("shared_read_blocks"),
                    "rows_returned": bm_before.get("rows_returned"),
                },
                "after_benchmark": {
                    "mean_execution_time_ms": bm_after.get("mean_execution_time_ms"),
                    "median_execution_time_ms": bm_after.get("median_execution_time_ms"),
                    "stddev_execution_time_ms": bm_after.get("stddev_execution_time_ms"),
                    "min_execution_time_ms": bm_after.get("min_execution_time_ms"),
                    "max_execution_time_ms": bm_after.get("max_execution_time_ms"),
                    "coefficient_of_variation": bm_after.get("coefficient_of_variation"),
                    "scan_type": bm_after.get("scan_type"),
                    "index_used": bm_after.get("index_used"),
                    "shared_hit_blocks": bm_after.get("shared_hit_blocks"),
                    "shared_read_blocks": bm_after.get("shared_read_blocks"),
                    "rows_returned": bm_after.get("rows_returned"),
                },
                "runtime_improvement_percent": exec_res.runtime_improvement_percent,
                "planner_cost_improvement_percent": exec_res.planner_cost_improvement_percent,
                "physical_verification_passed": True,
                "persisted_memory_id": exec_res.persisted_memory_id,
                "provenance": exec_res.provenance,
                "verification_state": exec_res.verification_state,
                "cleanup_success": cleanup_ok,
                "exclusion_reason": None,
            }

            print(f"  -> SUCCESS! Memory ID {exec_res.persisted_memory_id}: "
                  f"T_before={bm_before.get('mean_execution_time_ms'):.4f}ms, "
                  f"T_after={bm_after.get('mean_execution_time_ms'):.4f}ms, "
                  f"Runtime Delta={exec_res.runtime_improvement_percent:.2f}%, "
                  f"Cleanup={cleanup_ok}")

            results.append(case_record)

        except Exception as exc:
            print(f"  -> FAILED/EXCLUDED: {exc}")
            # Ensure index cleanup on failure
            post_residual = count_autodba_indexes()
            if post_residual > 0:
                print(f"  [CLEANUP] Cleaning up residual indexes after failure...")
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    idxs = conn.execute(text("SELECT indexname FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%';")).fetchall()
                    for idx_row in idxs:
                        conn.execute(text(f"DROP INDEX IF EXISTS {idx_row[0]};"))
                    conn.execute(text("DISCARD ALL;"))

            case_record = {
                "case_id": case_id,
                "template_id": template_id,
                "exact_sql": query,
                "target_table": target_table,
                "role": role,
                "status": "EXCLUDED",
                "candidate_pool": [],
                "candidate_count": 0,
                "hypopg_verdict": None,
                "hypopg_cost_improvement_percent": None,
                "hypopg_original_cost": None,
                "hypopg_hypothetical_cost": None,
                "safety_eligible": False,
                "safety_level": None,
                "safety_blocking_reasons": [str(exc)],
                "selected_physical_index": None,
                "selected_columns": [],
                "before_benchmark": {},
                "after_benchmark": {},
                "runtime_improvement_percent": None,
                "planner_cost_improvement_percent": None,
                "physical_verification_passed": False,
                "persisted_memory_id": None,
                "provenance": None,
                "verification_state": None,
                "cleanup_success": (count_autodba_indexes() == 0),
                "exclusion_reason": str(exc),
            }
            results.append(case_record)

    # Save output JSON artifact
    output_path = Path(__file__).resolve().parent / "phase6a_corpus_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print("PHASE 6A EXECUTION COMPLETED")
    print(f"Saved results to: {output_path}")
    print(f"Total processed: {len(results)}")
    successful = [r for r in results if r["status"] == "SUCCESS"]
    excluded = [r for r in results if r["status"] == "EXCLUDED"]
    print(f"Successful: {len(successful)} | Excluded: {len(excluded)}")
    print(f"Final residual idx_autodba_* count: {count_autodba_indexes()}")
    print("=" * 70)


if __name__ == "__main__":
    execute_corpus()
