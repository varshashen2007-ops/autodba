# AutoDBA — Phase 1 Implementation Plan

## 1. Existing Repository Structure & Inspection

A thorough inspection of the repository revealed the following initial state:

```text
AUTODBA/
├── README.md               # 12-line stub summarizing MVP concepts
├── docker-compose.yml      # Basic Compose with postgres:17, backend, and frontend
├── backend/
│   ├── Dockerfile          # python:3.12-slim based container
│   ├── requirements.txt    # fastapi, uvicorn, psycopg, pydantic-settings, langgraph, httpx, sqlalchemy
│   └── app/
│       ├── main.py         # Basic FastAPI stub with / and /api/health
│       ├── api/
│       │   └── health.py   # Simple {"status": "ok"} endpoint
│       ├── agents/         # Empty directory
│       ├── core/           # Empty directory
│       ├── db/             # Empty directory
│       ├── schemas/        # Empty directory
│       └── services/       # Empty directory
├── frontend/
│   ├── package.json        # React + Vite + TypeScript stub
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       └── style.css
├── postgres/
│   └── init/
│       └── 001_extensions.sql # "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
└── docs/
    └── ARCHITECTURE.md     # 6-line high-level architectural overview
```

### Key Inspection Findings:
1. **PostgreSQL Configuration**: The `postgres:17` image in `docker-compose.yml` does not load `pg_stat_statements` in `shared_preload_libraries`, which is strictly required for query statistics collection.
2. **HypoPG Availability**: Debian's package repository for `postgres:17` provides `postgresql-17-hypopg`. A lightweight custom `postgres/Dockerfile` can install this extension cleanly and reproducibly.
3. **Missing Environment Files**: Neither `.env` nor `.env.example` existed. Secrets were partially hardcoded in `docker-compose.yml`.
4. **Backend Stubs**: The backend lacked database connection logic, ORM models, Pydantic schemas, monitoring services, error handlers, and unit tests.
5. **Database Initialization**: Only `001_extensions.sql` was present; no tables or seed data existed.

---

## 2. What Will Be Changed

* **`docker-compose.yml`**:
  * Point `postgres` service to build from `postgres/Dockerfile` (to include HypoPG).
  * Add postgres command: `-c shared_preload_libraries=pg_stat_statements -c pg_stat_statements.track=all`.
  * Parameterize credentials using `.env` variables (`${POSTGRES_USER:-autodba}`, etc.).
  * Ensure robust healthchecks and dependency conditions.
* **`postgres/init/`**:
  * Replace stub `001_extensions.sql` with `01-init.sql` (enabling `pg_stat_statements` and `hypopg`, defining `customers`, `products`, `orders`, `order_items` tables with constraints).
  * Add `02-seed.sql` (generating realistic deterministic dataset for performance experiments).
* **`backend/requirements.txt`**:
  * Add testing and utility dependencies: `pytest`, `pytest-asyncio`, `python-dotenv`.
* **`backend/app/main.py`**:
  * Restructure to mount `/api/v1` router, configure OpenAPI metadata, and add centralized exception handling (safe error responses without stack traces or credential leaks).
* **`backend/app/api/health.py`**:
  * Update to route under `/api/v1/health` and verify real database connectivity.
* **`README.md`**:
  * Comprehensive documentation covering Phase 1 architecture, running locally, seeding, verification, and API reference.

---

## 3. What Will NOT Be Changed

* **`frontend/`**: Remains untouched during Phase 1. Frontend UI dashboards belong to Phase 2/3.
* **`backend/app/agents/`**: No LLM agents, LangGraph workflows, prompt templates, RAG, fine-tuning, or pgvector will be introduced in Phase 1.
* **`docs/ARCHITECTURE.md`**: Preserved as the overarching long-term vision document.

---

## 4. What Will Be Created

* **`postgres/Dockerfile`**: Clean Dockerfile based on `postgres:17` that installs `postgresql-17-hypopg`.
* **`.env.example`**: Standard environment variable template.
* **`.gitignore`**: Git ignore rules preventing `.env`, Python bytecode, caches, and database volumes from being committed.
* **`backend/app/core/config.py`**: Pydantic `BaseSettings` managing database URL, credentials, API prefix, and log levels.
* **`backend/app/core/logging.py`**: Structured logger formatting operation name, execution duration, and status without leaking secrets.
* **`backend/app/db/database.py`**: SQLAlchemy engine, session factory, pool management, and connectivity verification.
* **`backend/app/db/models.py`**: Declarative models for `Customer`, `Product`, `Order`, `OrderItem`.
* **`backend/app/schemas/monitor.py`**: Pydantic schemas for `SlowQuery`, `SlowQueryResponse`, `ExplainRequest`, `ExplainResponse`, `HealthResponse`, and `ErrorResponse`.
* **`backend/app/services/database_monitor.py`**:
  * Slow query retrieval from `pg_stat_statements` with response normalization.
  * Conservative query validation layer blocking destructive statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, `VACUUM`, `CALL`, `DO`, multi-statement semicolons).
  * `EXPLAIN (FORMAT JSON)` execution service.
* **`backend/app/api/v1/monitor.py`**: REST endpoints for `/slow-queries` and `/explain`.
* **`backend/app/api/v1/router.py`**: Aggregator router combining health and monitoring.
* **`backend/tests/`**:
  * `conftest.py`: Test fixtures and test client setup.
  * `test_health.py`: Database connectivity and health API tests.
  * `test_monitor.py`: Slow queries and EXPLAIN safety tests (verifying SELECT succeeds and destructive SQL is rejected).
  * `test_config.py`: Configuration validation tests.

---

## 5. Phase 1 Implementation Plan

1. **Infrastructure**:
   * Create `postgres/Dockerfile` with `postgresql-17-hypopg`.
   * Create `postgres/init/01-init.sql` with schema and extensions.
   * Create `postgres/init/02-seed.sql` with deterministic e-commerce workload.
   * Update `docker-compose.yml` with `shared_preload_libraries=pg_stat_statements` and env var defaults.
   * Create `.env.example` and `.gitignore`.
2. **Backend Foundation**:
   * Implement `backend/app/core/config.py` with Pydantic Settings.
   * Implement `backend/app/core/logging.py` with structured audit logging.
   * Implement `backend/app/db/database.py` and `backend/app/db/models.py`.
   * Implement Pydantic schemas in `backend/app/schemas/monitor.py`.
3. **Monitoring & Plan Analysis**:
   * Implement `backend/app/services/database_monitor.py` (pg_stat_statements normalization + conservative EXPLAIN validator).
   * Implement API endpoints in `backend/app/api/v1/` (`health.py`, `monitor.py`, `router.py`).
   * Wire routers and custom exception handlers into `backend/app/main.py`.
4. **Testing & Verification**:
   * Add test suite in `backend/tests/`.
   * Run unit and integration tests using `pytest`.
   * Execute acceptance tests against Dockerized PostgreSQL:
     * Health check passes.
     * Seed tables exist with expected data volume.
     * `pg_stat_statements` and `hypopg` extensions active.
     * Slow query API reports real database execution metrics.
     * `EXPLAIN` returns structured query plans for `SELECT`.
     * Destructive SQL (`DROP TABLE orders`) is rejected.
5. **Documentation & Final Reporting**:
   * Update `README.md`.
   * Complete walkthrough and final report.
