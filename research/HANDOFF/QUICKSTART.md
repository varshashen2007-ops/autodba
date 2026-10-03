# AutoDBA Research Pipeline — Quick Start

**Freeze date:** 2026-10-03  
**HEAD commit:** `2fec570`

This document lists only commands that exist in the repository and were verified to work
during Phase 6–8 execution. Nothing has been invented.

---

## 1. Environment Setup

### Python dependencies

The repository uses a standard `requirements.txt`. Install into a virtual environment:

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r research/requirements.txt
```

On Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r research/requirements.txt
```

`research/requirements.txt` (as committed at HEAD):
```
psycopg2-binary
sqlalchemy
pydantic
```

The full backend dependency set is managed by the Docker Compose stack in `autodba-main/`.

### Environment variable

The research scripts default to `localhost` for the PostgreSQL host:

```powershell
# Only needed if PostgreSQL is not on localhost:5432
$env:POSTGRES_HOST = "localhost"
```

---

## 2. PostgreSQL Startup

The database runs inside Docker Compose defined in `autodba-main/docker-compose.yml`:

```powershell
cd autodba-main
docker compose up -d postgres
```

Wait for the container to be healthy:

```powershell
docker compose ps
# postgres service should show: healthy
```

---

## 3. Database Readiness Checks

Verify that the PostgreSQL instance is ready and contains the expected research corpus.

### Check table existence and extension availability

```powershell
# From autodba-research root
$env:PYTHONIOENCODING = "utf-8"
python -c "
import os, sys
sys.path.insert(0, 'autodba-main/backend')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
from app.db.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    for tbl in ['orders', 'order_items', 'customers', 'products']:
        n = conn.execute(text(f'SELECT COUNT(*) FROM {tbl}')).scalar()
        print(f'  {tbl}: {n} rows')
    conn.execute(text('SELECT hypopg_reset()'))
    print('  HypoPG: OK')
    n = conn.execute(text('SELECT COUNT(*) FROM optimization_memories')).scalar()
    print(f'  optimization_memories: {n} rows (expected 14)')
"
```

### Verify the Phase 6C partition manifest hash

```powershell
python research\scratch\phase8_hash_verify.py
```

Expected output ends with:
```
VERDICT: T9 is a genuinely unseen template. Safe for Phase 8 TEST assignment.
```

### Verify Phase 8 artifact consistency

```powershell
$env:PYTHONIOENCODING = "utf-8"
python research\scratch\phase8_consistency_check.py
```

Expected output ends with:
```
VERDICT: ALL CHECKS PASSED
```

---

## 4. Running the Validated Research Pipeline

### Python path requirement

All research scripts must be run from the **repository root** (`autodba-research/`) using
`python -m` to ensure the `research` package and `autodba-main/backend` are on the path:

```powershell
# Always run from: C:\Users\swarsh\Desktop\autodba-research
$env:PYTHONIOENCODING = "utf-8"
```

### Import health check (read-only, no DB needed)

```powershell
python -c "
import sys, os
sys.path.insert(0, '.')
sys.path.insert(0, 'autodba-main/backend')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
from research.case_schema import canonicalize_sql, compute_template_hash, OptimizationCase
from research.candidate_selector import CandidateSelector, canonical_candidate_key
from research.split_strategy import grouped_template_split, verify_split_leakage
from research.baseline_retrieval import BaselineRetrievalMethods
from research.measured_case_runner import MeasuredCaseRunner, ResearchSafetyError
from research.evaluation_harness import EvaluationHarness
print('All research modules import OK')
"
```

---

## 5. Running the Research Execution Scripts

> [!IMPORTANT]
> Each execution script performs its own Phase 6C partition hash verification at startup.
> If the hash does not match, the script stops immediately with a blocker message.

### Phase 6D — Comparative A/B/C vs Oracle (TEST partition T7, T8)

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m research.execute_phase6d_experiment
```

This re-runs the Phase 6D experiment against the locked TEST partition. Results overwrite
`research/phase6d_measurements.json` and `research/phase6d_selection_results.json`.

> Note: Phase 6D is a historical result. Re-running will produce fresh benchmark numbers
> (which may differ slightly from the original due to timing variability) but the policy
> selections will be deterministic.

### Phase 7 — Targeted Measured-Corpus Execution

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m research.execute_phase7
```

### Phase 8 — Multi-Candidate Unseen-Template Experiment

```powershell
$env:PYTHONIOENCODING = "utf-8"
python -m research.execute_phase8
```

---

## 6. Inspecting Experiment Artifacts

All experiment artifacts are plain JSON and Markdown files in `research/`.

### View Phase 8 oracle and policy comparison

```powershell
python -c "
import json
from pathlib import Path
m = json.loads(Path('research/phase8_measurements.json').read_text())
print('Oracle:', m['oracle']['candidate_id'], m['oracle']['runtime_improvement_percent'], '%')
for k, v in m['policy_evaluations'].items():
    print(f'  {k}: regret={v[\"selection_regret_percent\"]}% OA={v[\"is_oracle\"]}')
"
```

### View Phase 8 policy scores (pre-measurement)

```powershell
python -c "
import json
from pathlib import Path
s = json.loads(Path('research/phase8_selection_results.json').read_text())[0]
for pol in ['policy_a', 'policy_b', 'policy_c']:
    sel = s['selections'][pol]
    print(f'{pol}: selected={sel[\"selected_candidate_id\"]} fallback={sel[\"fallback_used\"]}')
    for cs in sel['candidate_scores']:
        print(f'  {cs[\"canonical_key\"]}: composite_score={cs[\"composite_score\"]}')
"
```

### View Phase 6D comparative results

```powershell
python -c "
import json
from pathlib import Path
results = json.loads(Path('research/phase6d_measurements.json').read_text())
for r in results:
    print(r['case_id'], r['template_id'])
    print('  Oracle:', r['oracle']['candidate_id'], r['oracle']['runtime_improvement_percent'], '%')
    for pk in ['policy_a', 'policy_b', 'policy_c']:
        pe = r['policy_evaluations'][pk]
        print(f'  {pk}: dT={pe[\"runtime_improvement_percent\"]}% regret={pe[\"selection_regret_percent\"]}% OA={pe[\"is_oracle\"]}')
"
```

### View the Phase 6C partition manifest

```powershell
python -c "
import json
from pathlib import Path
m = json.loads(Path('research/phase6c_partition_manifest.json').read_text())
for part, info in m['partitions'].items():
    print(f'{part}: {info[\"case_count\"]} cases, templates={info[\"templates\"]}')
"
```

---

## 7. Checking Cleanup

### Verify no residual experimental indexes remain

```powershell
python -c "
import os, sys
sys.path.insert(0, 'autodba-main/backend')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
from app.db.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    n = conn.execute(text(\"SELECT COUNT(*) FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%'\")).scalar()
    rows = conn.execute(text(\"SELECT indexname FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%'\")).fetchall()
    print(f'Residual idx_autodba_* count: {n}')
    for r in rows:
        print(f'  {r[0]}')
"
```

Expected: count = 0

### Verify optimization_memories count

```powershell
python -c "
import os, sys
sys.path.insert(0, 'autodba-main/backend')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
from app.db.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    n = conn.execute(text('SELECT COUNT(*) FROM optimization_memories')).scalar()
    ids = conn.execute(text('SELECT id FROM optimization_memories ORDER BY id')).fetchall()
    print(f'optimization_memories count: {n} (expected 14)')
    print(f'IDs: {[r[0] for r in ids]}')
"
```

Expected: count = 14, IDs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
