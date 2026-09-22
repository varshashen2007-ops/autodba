# AutoDBA

AutoDBA is an automated database observability and DBA-assistance platform for PostgreSQL. It continuously monitors query performance, surfaces slow queries from `pg_stat_statements`, provides safe read-only execution plan analysis via HypoPG and `EXPLAIN`, and is designed as a foundation for an AI-powered self-improving DBA pipeline.

> **Current Phase:** Phase 3 Complete — Real Runtime Benchmarking  
> The full pipeline from query observation through HypoPG validation, recommendation, safety gating, human approval, physical index creation, and real measured before/after benchmarking is now implemented.

---

## Architecture (Phase 1)

```
Frontend (future)
       |
       v
FastAPI (port 8000)
       |
       +-- GET  /api/v1/health          Health + extension check
       |
       +-- GET  /api/v1/slow-queries    pg_stat_statements monitoring
       |
       +-- POST /api/v1/explain         SQL safety validator
                                              |
                                              +-- EXPLAIN (FORMAT JSON)
       |
       v
PostgreSQL 17 (port 5432)
       |
       +-- pg_stat_statements           Query execution statistics
       |
       +-- HypoPG                       Hypothetical index simulation
       |
       +-- E-commerce workload          customers / products / orders / order_items
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Web framework | FastAPI 0.115+ |
| ORM | SQLAlchemy 2.0 |
| Validation | Pydantic v2 + pydantic-settings |
| Database | PostgreSQL 17 |
| Query statistics | pg_stat_statements |
| Hypothetical indexing | HypoPG 1.4.3 |
| Containerisation | Docker + Docker Compose |
| Testing | pytest + pytest-asyncio |

---

## Running Locally

### Prerequisites
- Docker Desktop (or Docker Engine + Docker Compose v2)

### Start from scratch

```bash
# Clone and enter the project
cd AUTODBA

# Copy environment template
cp .env.example .env

# Build and start everything
docker compose up --build -d

# Check container health
docker compose ps
```

Both containers should be `Up (healthy)` within ~30 seconds.

### Verify PostgreSQL is ready

```bash
docker compose exec postgres psql -U autodba -d autodba -c "SELECT extname FROM pg_extension;"
```

Expected output includes `pg_stat_statements` and `hypopg`.

### Verify seed data

```bash
docker compose exec postgres psql -U autodba -d autodba \
  -c "SELECT 'customers' AS t, count(*) FROM customers UNION ALL \
      SELECT 'products', count(*) FROM products UNION ALL \
      SELECT 'orders', count(*) FROM orders UNION ALL \
      SELECT 'order_items', count(*) FROM order_items;"
```

Expected row counts:

| Table | Rows |
|-------|------|
| customers | 500 |
| products | 100 |
| orders | 5,000 |
| order_items | 15,000 |

### Reset the database

```bash
docker compose down -v
docker compose up --build -d
```

---

## Service URLs

| Service | URL |
|---------|-----|
| FastAPI backend | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| OpenAPI schema | http://localhost:8000/openapi.json |
| PostgreSQL | localhost:5432 |

---

## API Reference

### `GET /api/v1/health`

Returns application health and PostgreSQL connectivity status.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "PostgreSQL 17.11 ...",
  "extensions": ["hypopg", "pg_stat_statements", "plpgsql"]
}
```

---

### `GET /api/v1/slow-queries`

Returns top queries sorted by total execution time from `pg_stat_statements`.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 10 | Max number of queries (1–100) |
| `min_exec_time_ms` | float | 0.0 | Filter queries with `mean_exec_time >= threshold` |

**Example:**
```bash
curl "http://localhost:8000/api/v1/slow-queries?limit=5&min_exec_time_ms=1.0"
```

**Response:**
```json
{
  "queries": [
    {
      "query": "SELECT * FROM orders WHERE customer_id = $1",
      "calls": 5,
      "total_time_ms": 12.5,
      "mean_time_ms": 2.5,
      "rows": 50,
      "shared_blks_hit": 120,
      "shared_blks_read": 3
    }
  ],
  "count": 1
}
```

---

### `POST /api/v1/explain`

Validates that a SQL query is safe and read-only, then returns the PostgreSQL execution plan.

**Request:**
```json
{
  "query": "SELECT * FROM orders WHERE customer_id = 42"
}
```

**Response:**
```json
{
  "query": "SELECT * FROM orders WHERE customer_id = 42",
  "plan": [
    {
      "Plan": {
        "Node Type": "Seq Scan",
        "Relation Name": "orders",
        "Startup Cost": 0.0,
        "Total Cost": 107.5,
        "Plan Rows": 10,
        "Plan Width": 40,
        "Filter": "(customer_id = 42)"
      }
    }
  ],
  "planning_time_ms": null,
  "execution_time_ms": null
}
```

---

## SQL Safety

The `/api/v1/explain` endpoint enforces strict read-only access through a custom SQL tokenizer and validator. It never passes an unvalidated query to the database.

**Allowed:**
- `SELECT ...` statements
- Read-only CTEs (`WITH ... SELECT ...`)
- Trailing semicolons (stripped before analysis)
- String literals that happen to contain keywords (e.g. `WHERE name = 'DROP TABLE orders'`)

**Rejected (HTTP 400):**

| Category | Examples |
|----------|---------|
| DML | `INSERT`, `UPDATE`, `DELETE` |
| DDL | `CREATE`, `DROP`, `ALTER`, `TRUNCATE` |
| DCL | `GRANT`, `REVOKE` |
| Maintenance | `VACUUM`, `REINDEX`, `CLUSTER` |
| Execution | `CALL`, `DO`, `EXECUTE`, `COPY` |
| Multi-statement | `SELECT 1; DROP TABLE orders;` |
| Empty queries | `""`, `"   "`, comments only |

The validator uses a **lexical tokenizer** — not substring matching — so words inside quoted string literals or double-quoted identifiers do not trigger false positives.

---

## Testing

### Run the full test suite (inside Docker Compose)

```bash
docker compose run --rm backend pytest -v
```

### Run unit tests only (no database required)

```bash
docker run --rm autodba-backend pytest tests/test_config.py tests/test_models.py tests/test_schemas.py tests/test_sql_validator.py -v
```

### Test coverage

| Test file | What it tests |
|-----------|--------------|
| `test_acceptance.py` | Full end-to-end acceptance: infrastructure, monitoring, EXPLAIN, security, integrity |
| `test_monitor_api.py` | Monitoring + EXPLAIN API endpoint integration |
| `test_sql_validator.py` | SQL tokenizer and validator unit tests |
| `test_health.py` | Health endpoint (mocked healthy and degraded states) |
| `test_config.py` | Pydantic Settings and credential masking |
| `test_database.py` | SQLAlchemy session lifecycle |
| `test_models.py` | ORM model metadata and repr |
| `test_schemas.py` | Pydantic schema validation |

---

## Environment Variables

Copy `.env.example` to `.env` and adjust if needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `postgres` | PostgreSQL container hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `autodba` | Database name |
| `POSTGRES_USER` | `autodba` | Database user |
| `POSTGRES_PASSWORD` | `autodba` | Database password (change for production) |
| `LOG_LEVEL` | `INFO` | Application log level |
| `API_V1_PREFIX` | `/api/v1` | API route prefix |

---

## Development Schema

The development database contains a deterministic e-commerce schema:

```sql
customers   (id, name, email, created_at)
products    (id, name, category, price, stock, created_at)
orders      (id, customer_id, order_date, total_amount, status)
order_items (id, order_id, product_id, quantity, unit_price)
```

The `orders.customer_id` column is **intentionally unindexed** — this demonstrates a sequential scan that AutoDBA will later detect and remediate via HypoPG.

---

## Phase Completion Status

| Phase | Step | Description | Tests |
|-------|------|-------------|-------|
| 1 | — | PostgreSQL Foundation & Monitoring Infrastructure | 94 |
| 2 | 1 | Execution Plan Intelligence | 132 |
| 2 | 2 | HypoPG Counterfactual Validation | 160 |
| 2 | 3 | Optimization Recommendation Engine | 203 |
| 3 | 1 | Safety & Human Approval Gate | 234 |
| 3 | 2 | Controlled Physical Remediation | 254 |
| 3 | 3 | Real Runtime Benchmarking | **285** |

All 285 tests pass. Zero failures.

---

## Phase 3.3 — Real Runtime Benchmarking

### Overview

Phase 3.3 closes the evidence loop: after a physical index is created by Phase 3.2, the system measures the real query runtime **before** and **after** the remediation using controlled `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` repeated runs. This produces a grounded, auditable benchmark result — not a planner estimate.

### Measured Benchmark: `SELECT * FROM orders WHERE customer_id = 42`

This canonical query against a 5,000-row `orders` table with `customer_id = 42` (10 matching rows) was benchmarked with **10 runs + 2 warm-up runs** after the physical index `idx_autodba_orders_customer_id` was created in Phase 3.2.

| Metric | BEFORE (Seq Scan) | AFTER (Bitmap Index Scan) | Improvement |
|--------|-------------------|---------------------------|-------------|
| Mean execution time | 0.1289 ms | 0.0156 ms | **87.9%** |
| Median execution time | 0.1225 ms | 0.0155 ms | **87.3%** |
| Min execution time | 0.1180 ms | 0.0150 ms | — |
| Max execution time | 0.1670 ms | 0.0170 ms | — |
| Stddev | 0.0148 ms | 0.0007 ms | — |
| Planner cost | 107.50 | 28.41 | **73.6%** |
| Shared hit blocks | 45 | 14 | — |
| Scan type | `Seq Scan` | `Bitmap Heap Scan` | — |
| Index used | — | `idx_autodba_orders_customer_id` | — |

### Benchmarking Methodology

#### Controlled Baseline (BEFORE)

The BEFORE measurement simulates the pre-index state without dropping or mutating the physical index using PostgreSQL session-local scan flags:

```sql
SET LOCAL enable_indexscan = off;
SET LOCAL enable_bitmapscan = off;
```

These settings are **transaction-local** — they expire at transaction commit and make zero permanent changes to the database. The planner is forced to produce a sequential scan plan, which represents the counterfactual baseline accurately.

#### Warm-Up Runs

The first `BENCHMARK_WARMUP_RUNS` (default: 2) query executions are discarded. This stabilises the shared buffer pool (filling the OS page cache and PostgreSQL buffer cache) so measured runs reflect steady-state performance, not cold-start I/O overhead.

#### Measurement Runs

`BENCHMARK_RUNS` (default: 10) full `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` executions are collected. Statistics computed per phase:

- **Mean**, **Median**, **Min**, **Max**, **Stddev** of execution times
- **Coefficient of Variation** (Stddev / Mean) to flag noisy runs

#### Planner Cost vs. Runtime Improvement

These two metrics are **explicitly separate** and must not be conflated:

| Metric | Source | Meaning |
|--------|--------|---------|
| `planner_cost_improvement_percent` | PostgreSQL planner estimate | How much the query cost estimate dropped (HypoPG predicts this) |
| `runtime_improvement_percent` | `EXPLAIN ANALYZE` measured wall time | How much the actual query execution time improved |

The planner cost improvement (73.6%) predicted by HypoPG in Phase 2.2 closely matched the measured runtime improvement (87.9%), validating the end-to-end pipeline from hypothetical simulation to real execution.

#### Zero Database Mutation

Benchmarking is strictly read-only:
- No DDL is executed
- No indexes are created or dropped
- All scan flags use `SET LOCAL` (transaction-scoped, auto-reverted)
- The benchmark validates query safety via the Phase 1 SQL validator before execution

### BenchmarkService API

```python
from app.services.benchmark_service import BenchmarkService

result = BenchmarkService.benchmark(
    query="SELECT * FROM orders WHERE customer_id = 42;",
    remediation=remediation_result,  # Optional: AppliedRemediationResult
    runs=10,
    warmup_runs=2,
)

# result.status                         → BenchmarkStatus.COMPLETED
# result.runtime_improvement_percent    → 87.9
# result.planner_cost_improvement_percent → 73.57
# result.plan_changed                   → True
# result.index_usage_changed            → True
# result.before.scan_type               → "Seq Scan"
# result.after.scan_type                → "Bitmap Heap Scan"
# result.after.index_used               → "idx_autodba_orders_customer_id"
```

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `BENCHMARK_RUNS` | `10` | Number of measured execution runs |
| `BENCHMARK_WARMUP_RUNS` | `2` | Warm-up runs discarded before measurement |



## Project Structure

```text
AUTODBA/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── health.py                  Health endpoint
│   │   │   └── v1/
│   │   │       ├── monitor.py             Monitoring endpoints
│   │   │       └── router.py              v1 router aggregator
│   │   ├── core/
│   │   │   ├── config.py                  Pydantic Settings (incl. benchmark config)
│   │   │   ├── exceptions.py              Domain exceptions
│   │   │   └── logging.py                 Structured JSON logging
│   │   ├── db/
│   │   │   ├── database.py                SQLAlchemy engine + sessions
│   │   │   └── models.py                  ORM models
│   │   ├── schemas/
│   │   │   ├── monitor.py                 Phase 1 monitoring schemas
│   │   │   └── optimization.py            Phase 2–3 optimization pipeline schemas
│   │   ├── services/
│   │   │   ├── database_monitor.py        pg_stat_statements + EXPLAIN
│   │   │   ├── sql_validator.py           Read-only SQL tokenizer/validator
│   │   │   ├── plan_analyzer.py           Execution plan parsing (Phase 2.1)
│   │   │   ├── bottleneck_detector.py     Bottleneck classification (Phase 2.1)
│   │   │   ├── hypopg_service.py          HypoPG counterfactual validation (Phase 2.2)
│   │   │   ├── recommendation_engine.py   Optimization recommendation (Phase 2.3)
│   │   │   ├── safety_assessor.py         Safety rule evaluation (Phase 3.1)
│   │   │   ├── approval_service.py        Human approval gate (Phase 3.1)
│   │   │   ├── remediation_service.py     Physical index creation (Phase 3.2)
│   │   │   └── benchmark_service.py       Before/after benchmarking (Phase 3.3)
│   │   └── main.py                        FastAPI app + exception handlers
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_acceptance.py
│   │   ├── test_config.py
│   │   ├── test_database.py
│   │   ├── test_health.py
│   │   ├── test_models.py
│   │   ├── test_monitor_api.py
│   │   ├── test_schemas.py
│   │   ├── test_sql_validator.py
│   │   ├── test_plan_analyzer.py
│   │   ├── test_bottleneck_detector.py
│   │   ├── test_hypopg_service.py
│   │   ├── test_recommendation_engine.py
│   │   ├── test_safety_assessor.py
│   │   ├── test_approval_service.py
│   │   ├── test_remediation_service.py
│   │   └── test_benchmark_service.py
│   ├── Dockerfile
│   └── requirements.txt
├── postgres/
│   ├── Dockerfile                     postgres:17 + postgresql-17-hypopg
│   └── init/
│       ├── 01-init.sql                Extensions + schema
│       └── 02-seed.sql                Deterministic dataset
├── docs/
│   ├── ARCHITECTURE.md
│   └── PHASE1_PLAN.md
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```
