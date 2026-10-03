import hashlib
import json
import os
from pathlib import Path
import sys

root_path = Path.cwd()
backend_path = root_path / "backend"
sys.path.insert(0, str(root_path))
sys.path.insert(0, str(backend_path))
os.environ["POSTGRES_HOST"] = "localhost"

from app.db.database import SessionLocal
from sqlalchemy import text
from research.case_schema import canonicalize_sql

db = SessionLocal()
rows = db.execute(text(
    "SELECT id, incident_type, query_fingerprint, query_text, diagnosis, recommendation, "
    "validation, benchmark, outcome, outcome_summary, provenance, is_verified, verification_state, created_at "
    "FROM optimization_memories ORDER BY id"
)).mappings().fetchall()

# Map memory ID to template and partition
# T1: IDs 1, 2, 3 (TRAIN)
# T2: IDs 4, 5, 6 (TRAIN)
# T3: ID 7 (DEV)
# T5: IDs 8, 9 (DEV)
# T7: IDs 10, 11, 12 (TEST)
# T8: IDs 13, 14 (TEST)

partition_map = {
    1: ("CASE-T1-01", "T1", "TRAIN"),
    2: ("CASE-T1-02", "T1", "TRAIN"),
    3: ("CASE-T1-03", "T1", "TRAIN"),
    4: ("CASE-T2-01", "T2", "TRAIN"),
    5: ("CASE-T2-02", "T2", "TRAIN"),
    6: ("CASE-T2-03", "T2", "TRAIN"),
    7: ("CASE-T3-03", "T3", "DEV"),
    8: ("CASE-T5-01", "T5", "DEV"),
    9: ("CASE-T5-02", "T5", "DEV"),
    10: ("CASE-T7-01", "T7", "TEST"),
    11: ("CASE-T7-02", "T7", "TEST"),
    12: ("CASE-T7-03", "T7", "TEST"),
    13: ("CASE-T8-01", "T8", "TEST"),
    14: ("CASE-T8-02", "T8", "TEST"),
}

manifest_cases = []
for r in rows:
    mid = r["id"]
    if mid not in partition_map:
        continue
    case_id, template_id, partition = partition_map[mid]
    c_sql = canonicalize_sql(r["query_text"])
    t_hash = hashlib.sha256(c_sql.encode("utf-8")).hexdigest()
    
    rec = r["recommendation"] or {}
    table = (rec.get("relation") or "orders").lower()
    cols = [c.lower() for c in (rec.get("columns") or [])]
    cand_key = f"{table}:btree:{','.join(cols)}"

    manifest_cases.append({
        "case_id": case_id,
        "template_id": template_id,
        "memory_id": mid,
        "partition": partition,
        "query_text": r["query_text"],
        "canonical_template": c_sql,
        "template_hash": t_hash,
        "target_table": table,
        "primary_candidate_key": cand_key,
        "provenance": r["provenance"],
        "is_verified": r["is_verified"],
        "verification_state": r["verification_state"],
    })

manifest = {
    "manifest_version": "1.0.0",
    "created_at": "2026-10-01T22:30:00Z",
    "total_cases": len(manifest_cases),
    "partitions": {
        "TRAIN": {
            "case_count": len([c for c in manifest_cases if c["partition"] == "TRAIN"]),
            "templates": sorted(list(set(c["template_id"] for c in manifest_cases if c["partition"] == "TRAIN"))),
            "case_ids": [c["case_id"] for c in manifest_cases if c["partition"] == "TRAIN"],
            "memory_ids": [c["memory_id"] for c in manifest_cases if c["partition"] == "TRAIN"],
        },
        "DEV": {
            "case_count": len([c for c in manifest_cases if c["partition"] == "DEV"]),
            "templates": sorted(list(set(c["template_id"] for c in manifest_cases if c["partition"] == "DEV"))),
            "case_ids": [c["case_id"] for c in manifest_cases if c["partition"] == "DEV"],
            "memory_ids": [c["memory_id"] for c in manifest_cases if c["partition"] == "DEV"],
        },
        "TEST": {
            "case_count": len([c for c in manifest_cases if c["partition"] == "TEST"]),
            "templates": sorted(list(set(c["template_id"] for c in manifest_cases if c["partition"] == "TEST"))),
            "case_ids": [c["case_id"] for c in manifest_cases if c["partition"] == "TEST"],
            "memory_ids": [c["memory_id"] for c in manifest_cases if c["partition"] == "TEST"],
        },
    },
    "cases": manifest_cases,
}

manifest_path = root_path / "research" / "phase6c_partition_manifest.json"
manifest_json_str = json.dumps(manifest, indent=2, sort_keys=True)

with open(manifest_path, "w", encoding="utf-8") as f:
    f.write(manifest_json_str)

# Calculate SHA-256 of the manifest file
with open(manifest_path, "rb") as f:
    manifest_sha256 = hashlib.sha256(f.read()).hexdigest()

print(f"Generated {manifest_path}")
print(f"Manifest SHA-256: {manifest_sha256}")
print(f"Total Cases: {manifest['total_cases']}")
print(f"TRAIN: {manifest['partitions']['TRAIN']['case_count']} cases across {manifest['partitions']['TRAIN']['templates']}")
print(f"DEV: {manifest['partitions']['DEV']['case_count']} cases across {manifest['partitions']['DEV']['templates']}")
print(f"TEST: {manifest['partitions']['TEST']['case_count']} cases across {manifest['partitions']['TEST']['templates']}")

# Verification of Invariants
train_temps = set(manifest["partitions"]["TRAIN"]["templates"])
dev_temps = set(manifest["partitions"]["DEV"]["templates"])
test_temps = set(manifest["partitions"]["TEST"]["templates"])

train_cases_set = set(manifest["partitions"]["TRAIN"]["case_ids"])
dev_cases_set = set(manifest["partitions"]["DEV"]["case_ids"])
test_cases_set = set(manifest["partitions"]["TEST"]["case_ids"])

assert train_temps.isdisjoint(dev_temps), "TRAIN and DEV templates overlap!"
assert train_temps.isdisjoint(test_temps), "TRAIN and TEST templates overlap!"
assert dev_temps.isdisjoint(test_temps), "DEV and TEST templates overlap!"

assert train_cases_set.isdisjoint(dev_cases_set), "TRAIN and DEV cases overlap!"
assert train_cases_set.isdisjoint(test_cases_set), "TRAIN and TEST cases overlap!"
assert dev_cases_set.isdisjoint(test_cases_set), "DEV and TEST cases overlap!"

print("\nAll Partition Invariants 100% VERIFIED!")
db.close()
