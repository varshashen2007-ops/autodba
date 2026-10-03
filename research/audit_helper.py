import os, sys, json
from pathlib import Path
root_path = Path.cwd()
backend_path = root_path / 'backend'
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(backend_path))
os.environ['POSTGRES_HOST'] = 'localhost'

from app.db.database import SessionLocal, engine
from sqlalchemy import text
from research.case_schema import canonicalize_sql
from app.services.intelligence_service import IntelligenceService
from app.services.llm_service import LLMService
from research.measured_case_runner import ResearchExplanationProvider
from app.schemas.optimization import DiagnoseRequest

db = SessionLocal()
rows = db.execute(text('SELECT id, incident_type, query_fingerprint, query_text, diagnosis, recommendation, validation, benchmark, outcome, outcome_summary, provenance, is_verified, verification_state, created_at FROM optimization_memories ORDER BY id')).mappings().fetchall()

cases = []
for r in rows:
    c_sql = canonicalize_sql(r['query_text'])
    bm = r['benchmark'] or {}
    b_before = bm.get('before') or {}
    b_after = bm.get('after') or {}
    rec = r['recommendation'] or {}
    val = r['validation'] or {}
    diag = r['diagnosis'] or {}

    table = (rec.get('relation') or 'orders').lower()
    cols = tuple(c.lower() for c in (rec.get('columns') or []))
    cand_key = (table, 'btree', cols)

    cases.append({
        "id": r["id"],
        "query_text": r["query_text"],
        "canonical_sql": c_sql,
        "provenance": r["provenance"],
        "is_verified": r["is_verified"],
        "verification_state": r["verification_state"],
        "outcome": r["outcome"],
        "candidate_key": cand_key,
        "index_name": rec.get("index_name"),
        "t_before": b_before.get("mean_execution_time_ms"),
        "cov_before": b_before.get("coefficient_of_variation"),
        "runs_before": b_before.get("runs"),
        "warmup_before": b_before.get("warmup_runs"),
        "scan_before": b_before.get("scan_type"),
        "hit_before": b_before.get("shared_hit_blocks"),
        "read_before": b_before.get("shared_read_blocks"),
        "rows_before": b_before.get("rows_returned"),
        "t_after": b_after.get("mean_execution_time_ms"),
        "cov_after": b_after.get("coefficient_of_variation"),
        "runs_after": b_after.get("runs"),
        "warmup_after": b_after.get("warmup_runs"),
        "scan_after": b_after.get("scan_type"),
        "hit_after": b_after.get("shared_hit_blocks"),
        "read_after": b_after.get("shared_read_blocks"),
        "rows_after": b_after.get("rows_returned"),
        "runtime_improvement_percent": bm.get("runtime_improvement_percent"),
        "planner_cost_improvement_percent": bm.get("planner_cost_improvement_percent"),
        "diagnosis_present": bool(diag),
        "recommendation_present": bool(rec),
        "validation_present": bool(val),
        "benchmark_present": bool(bm),
    })

# Group by template
templates = {}
for c in cases:
    t = c['canonical_sql']
    if t not in templates:
        templates[t] = []
    templates[t].append(c['id'])

train_cases = [c for c in cases if c['id'] in [1, 2, 3, 4, 5, 6, 7, 8, 9]]
test_cases = [c for c in cases if c['id'] in [10, 11, 12, 13, 14]]

train_keys = {}
for c in train_cases:
    k_str = f"{c['candidate_key'][0]}:{c['candidate_key'][1]}:{','.join(c['candidate_key'][2])}"
    if k_str not in train_keys:
        train_keys[k_str] = []
    train_keys[k_str].append(c['id'])

intel = IntelligenceService(db, llm_service=LLMService(provider=ResearchExplanationProvider()))

test_support = []
for tc in test_cases:
    diag_resp = intel.diagnose(request=DiagnoseRequest(query=tc['query_text'], incident_type="missing_index", include_rag=False))
    cands = diag_resp.diagnosis.candidate_evaluations or []
    cand_info = []
    for ce in cands:
        rec_cols = tuple(c.lower() for c in (ce.recommendation.columns or []))
        rec_table = ce.recommendation.relation.lower()
        key = (rec_table, 'btree', rec_cols)
        k_str = f"{key[0]}:{key[1]}:{','.join(key[2])}"
        matching_train = train_keys.get(k_str, [])
        cost_impr = ce.validation.comparison.cost_improvement_percent if (ce.validation and ce.validation.comparison) else None
        cand_info.append({
            "candidate_id": ce.candidate_id,
            "is_baseline": ce.is_baseline,
            "key": key,
            "hypopg_verdict": ce.validation.verdict.value if ce.validation else None,
            "hypopg_cost_delta": cost_impr,
            "safety_eligible": ce.safety_assessment.eligible_for_approval if ce.safety_assessment else False,
            "matching_train_memory_ids": matching_train,
        })
    test_support.append({
        "test_memory_id": tc["id"],
        "query_text": tc["query_text"],
        "canonical_sql": tc["canonical_sql"],
        "candidate_count": len(cands),
        "candidates": cand_info,
    })

audit_data = {
    "total_db_records": len(rows),
    "cases": cases,
    "templates": templates,
    "train_keys": train_keys,
    "test_support": test_support,
}

with open("research/audit_dump.json", "w", encoding="utf-8") as f:
    json.dump(audit_data, f, indent=2)

print("Dumped audit to research/audit_dump.json successfully.")
db.close()
