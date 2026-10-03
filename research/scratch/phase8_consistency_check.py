"""
Phase 8 artifact consistency check — read-only, no DB access.
"""
import json, hashlib, sys
from pathlib import Path

r = Path("research")
ok = True

def chk(label, cond, detail=""):
    global ok
    status = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))

print("=" * 60)
print("PHASE 8 ARTIFACT CONSISTENCY CHECK")
print("=" * 60)

# Phase 6C hash
p6c = r / "phase6c_partition_manifest.json"
actual = hashlib.sha256(p6c.read_bytes()).hexdigest()
expected = "b91429205d36f572e5108bd7a66771f001de89631b810ac26d111771ce8c3d27"
chk("Phase 6C manifest hash", actual == expected, f"actual={actual[:20]}...")

# Phase 8 artifacts exist
for fname in ["phase8_selection_results.json", "phase8_measurements.json",
              "PHASE8_EXECUTION_REPORT.md", "PHASE8_FINAL_AUDIT.md",
              "PHASE8_MULTI_CANDIDATE_DESIGN.md", "PHASE8_PRE_EXECUTION_AUDIT.md",
              "phase8_experiment_manifest.json"]:
    chk(f"Artifact exists: {fname}", (r / fname).exists())

# Selection results integrity
sel = json.loads((r / "phase8_selection_results.json").read_text())[0]
chk("T9 template hash in selection", 
    sel["template_hash"] == "8aabaf56804e4478ebb2c6e90e5e4311c1a945b1cb71cc026fc4979453955343")
chk("Eligible count = 3", sel["eligible_count"] == 3)
chk("All 3 policies selected composite",
    all(sel["selections"][p]["selected_candidate_id"] == "cand_orders_total_amount_customer_id"
        for p in ["policy_a", "policy_b", "policy_c"]))
chk("No fallback used (A)", not sel["selections"]["policy_a"]["fallback_used"])
chk("No fallback used (B)", not sel["selections"]["policy_b"]["fallback_used"])
chk("No fallback used (C)", not sel["selections"]["policy_c"]["fallback_used"])
chk("Policy B had TRAIN matches", 
    sel["selections"]["policy_b"]["historical_support"].get("matching_history_cases", 0) == 6)
chk("Policy C had eligible measured matches",
    sel["selections"]["policy_c"]["historical_support"].get("matching_measured_cases", 0) == 6)

# Measurements integrity
meas = json.loads((r / "phase8_measurements.json").read_text())
chk("Same run_id in selection and measurements", sel["run_id"] == meas["run_id"])
chk("3 candidate benchmarks", len(meas["candidate_benchmarks"]) == 3)
chk("All cleanups succeeded",
    all(b["cleanup_success"] for b in meas["candidate_benchmarks"]))
chk("Post-run memory count = 14", meas["post_run_memory_count"] == 14)
chk("Post-run residual indexes = 0", meas["post_run_residual_indexes"] == 0)
chk("Memory isolation OK", meas["memory_isolation_ok"])

# Oracle
oracle = meas["oracle"]
chk("Oracle = composite", oracle["candidate_id"] == "cand_orders_total_amount_customer_id")
chk("Oracle dT% = 56.55", oracle["runtime_improvement_percent"] == 56.55)
chk("No tie in oracle", not oracle["is_tie"])

# Expected dT% values
bm_by_key = {b["canonical_key"]: b for b in meas["candidate_benchmarks"]}
chk("Composite dT% = 56.55", bm_by_key["orders:btree:total_amount,customer_id"]["runtime_improvement_percent"] == 56.55)
chk("customer_id dT% = 42.08", bm_by_key["orders:btree:customer_id"]["runtime_improvement_percent"] == 42.08)
chk("total_amount dT% = 35.38", bm_by_key["orders:btree:total_amount"]["runtime_improvement_percent"] == 35.38)

# Policy evaluations
for pk in ["policy_a", "policy_b", "policy_c"]:
    pe = meas["policy_evaluations"][pk]
    chk(f"{pk} regret = 0.0", pe["selection_regret_percent"] == 0.0)
    chk(f"{pk} is_oracle = True", pe["is_oracle"])

print()
print(f"VERDICT: {'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
sys.exit(0 if ok else 1)
