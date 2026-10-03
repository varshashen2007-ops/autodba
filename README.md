# AutoDBA — Autonomous PostgreSQL Optimization System

> **Production-grade, deterministic AI-driven query optimization with empirical benchmark evidence, human safety gates, and closed-loop learning.**

[![Backend Tests](https://img.shields.io/badge/backend%20tests-295%20passed-brightgreen)]()
[![Phase 8 Research](https://img.shields.io/badge/phase%208%20research-31%2F31%20passed-brightgreen)]()
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-blue)]()
[![Python](https://img.shields.io/badge/Python-3.11-blue)]()

---

## Overview

AutoDBA is a fully autonomous PostgreSQL performance optimization system that combines:

- **Deterministic EXPLAIN plan analysis** — no hallucinated bottleneck claims
- **HypoPG counterfactual index simulation** — virtual index cost estimation before applying any DDL
- **Human approval safety gate** — no DDL is executed without explicit operator sign-off
- **Physical remediation with real runtime benchmarking** — 10 runs + 2 warmups per change
- **RAG-grounded LLM reasoning** — historical optimization outcomes injected into Groq LLM context
- **Provenance-tracked memory** — every optimization memory carries its evidence chain (Policy A / B / C)
- **Closed-loop learning** — empirically verified outcomes automatically improve future diagnoses

---

## Architecture: 10-Stage Deterministic Pipeline

```
Stage 1:  pg_stat_statements collection
          → SQL safety validation
Stage 2:  EXPLAIN plan analysis (deterministic bottleneck detection)
Stage 3:  Multi-candidate evaluation (up to 5 strategies ranked by cost reduction)
Stage 4:  HypoPG virtual index simulation (counterfactual cost estimation)
Stage 5:  Safety assessment (DDL risk classification, blast radius)
Stage 6:  Human approval gate (operator must explicitly approve or reject)
Stage 7:  Physical DDL remediation (CREATE INDEX CONCURRENTLY)
Stage 8:  Real runtime benchmarking (10 queries × 2 warmups, median latency)
Stage 9:  Outcome verification (confirmed speedup measured empirically)
Stage 10: RAG memory storage (vectorized + provenance-tagged into PostgreSQL)
```

Every stage is **deterministic and auditable**. No stage is skipped. The LLM
(Groq · openai/gpt-oss-120b) is consulted only for natural-language recommendation
synthesis and is always grounded by real EXPLAIN plan output and retrieved historical
cases — it cannot bypass the HypoPG or benchmark gates.

---

## Provenance & Verification System (Policy A / B / C)

AutoDBA tracks the **evidence chain** for every optimization memory:

| Policy     | Provenance   | Verification State      | Source                                                     |
|------------|-------------|-------------------------|------------------------------------------------------------|
| **Policy A** | `measured`  | `verified_measured`     | Ran the full 10-stage pipeline; benchmark confirmed        |
| **Policy B** | `seeded`    | `synthetic`/`unverified`| Pre-loaded expert knowledge, not yet measured              |
| **Policy C** | —           | `verified_measured` only| RAG search restricted to empirically confirmed cases       |

### Provenance Values

| Value        | Meaning                                                        |
|--------------|---------------------------------------------------------------|
| `measured`   | AutoDBA ran the full remediation + benchmark cycle            |
| `seeded`     | Manually seeded expert case (trusted but not empirically confirmed) |
| `synthetic`  | AI-synthesized training case                                  |
| `unverified` | Memory created without a completed benchmark                  |

### Verification State Values

| Value              | Meaning                                                 |
|--------------------|---------------------------------------------------------|
| `verified_measured`| Empirical benchmark confirms the reported speedup       |
| `synthetic`        | Outcome based on synthetic or seeded data               |
| `unverified`       | No benchmark has been run against this memory           |

### Invariants (never violated by the backend)

1. A memory can only be `verified_measured` if Stage 8 benchmarking completed successfully.
2. `provenance = measured` ⟹ `verification_state = verified_measured`.
3. Policy C RAG searches return **only** `verified_measured` memories.
4. HypoPG must approve before any DDL reaches the human approval gate.
5. The human approval gate must be explicitly `approved` before physical remediation.

---

## Quick Start

### Prerequisites

- Docker Desktop (with Compose V2)
- A Groq API key — free tier at <https://console.groq.com>

### 1. Clone and configure

```bash
git clone https://github.com/your-org/autodba.git
cd autodba
cp .env.example .env
# Edit .env and set GROQ_API_KEY
```

### 2. Start all services

```bash
docker compose up --build -d
```

This starts three containers:

| Container            | Port | Purpose                                         |
|----------------------|------|-------------------------------------------------|
| `autodba-postgres-1` | 5432 | PostgreSQL 17 + pg_stat_statements + HypoPG    |
| `autodba-backend-1`  | 8000 | FastAPI backend (10-stage pipeline)             |
| `autodba-frontend-1` | 5173 | React + Vite dashboard                          |

### 3. Verify healthy

```bash
docker compose ps
curl http://localhost:8000/api/v1/health
```

### 4. Open the dashboard

Navigate to **http://localhost:5173** in your browser.

---

## Frontend Dashboard

The AutoDBA frontend is a dark-mode professional observability UI with six views:

### Dashboard
- Live PostgreSQL health + extensions (pg_stat_statements, HypoPG)
- Optimization memory count with provenance badges (`✓ VERIFIED`, `SEEDED`)
- Empirically measured speedup from Phase 8 benchmarks
- Pending human approvals counter (safety gate status)
- Recent optimization memories with inline provenance badges
- Slow query list from `pg_stat_statements`

### Investigate
- Paste any slow query for full EXPLAIN plan analysis
- **Multi-candidate evaluation card** — up to 5 ranked optimization strategies, each with:
  - HypoPG counterfactual cost (original vs. hypothetical planner cost, % improvement)
  - Safety gate result (LOW / MEDIUM / HIGH risk classification)
  - "Request Approval" button (sends to Stage 6 human gate)
- RAG historical cases panel with provenance/verification badges per case

### Approvals
- Queue of pending human approval requests
- Approve or reject each DDL with one click
- Approved actions proceed to physical remediation (Stage 7)

### Closed Loop
- Execute the full 10-stage pipeline end-to-end for a query
- Shows `VERIFIED MEASURED` + `Policy C Eligible` badges when benchmark completes
- DDL executed, runtime speedup (before/after median latency)
- Empirical Benchmark Evidence card: "Stage 8 — 10 Runs + 2 Warmups Measured"
- Full verification state, provenance, post-DDL verification result

### Intelligence (RAG Explorer)
- Semantic case matching against the memory corpus
- Filters: incident type bias, minimum cosine similarity threshold
- **Verified Measured Only (Policy C)** toggle — restricts results to empirically confirmed cases
- Each matched case shows provenance/verification badge

### Memory Explorer
- Full listing of all stored optimization memories
- Filter by: incident type, outcome, verification state
- Verification State column with colored badges
- Click any row to open provenance/verification telemetry modal

---

## Demo Steps

1. **Run end-to-end**: Go to **Closed Loop** → enter a slow query → click "Execute Closed Loop"
2. **Inspect candidates**: Go to **Investigate** → paste the same query → see ranked candidates with HypoPG cost estimates
3. **Human approval**: After requesting approval, check **Approvals** → approve the DDL
4. **RAG search**: Go to **Intelligence** → enable "Verified Measured Only" → search for similar cases
5. **Memory audit**: Go to **Memory Explorer** → filter to `Verified Measured` → click a row for full provenance telemetry

---

## Backend API Reference

| Method | Endpoint                                | Description                                              |
|--------|-----------------------------------------|----------------------------------------------------------|
| GET    | `/api/v1/health`                        | PostgreSQL connectivity, extension status                |
| GET    | `/api/v1/monitoring/slow-queries`       | pg_stat_statements top slow queries                      |
| POST   | `/api/v1/intelligence/diagnose`         | Full EXPLAIN analysis + multi-candidate evaluation       |
| GET    | `/api/v1/intelligence/memories`         | List all optimization memories                           |
| GET    | `/api/v1/intelligence/memories/{id}`    | Get single memory with full provenance                   |
| POST   | `/api/v1/intelligence/search`           | Semantic RAG search (`verified_only`, `provenance` filters) |
| POST   | `/api/v1/intelligence/closed-loop`      | Full 10-stage pipeline execution                         |
| GET    | `/api/v1/approvals`                     | List pending approval requests                           |
| POST   | `/api/v1/approvals/{id}/approve`        | Approve a DDL for physical remediation                   |
| POST   | `/api/v1/approvals/{id}/reject`         | Reject a DDL                                             |

---

## Database Schema

### `optimization_memories`

| Column                   | Type        | Description                                                       |
|--------------------------|-------------|-------------------------------------------------------------------|
| `id`                     | SERIAL      | Primary key                                                       |
| `query_text`             | TEXT        | The query that was optimized                                      |
| `incident_type`          | VARCHAR     | Bottleneck class (e.g., `missing_index`)                         |
| `outcome`                | VARCHAR     | Result (e.g., `index_created`)                                   |
| `embedding`              | FLOAT8[]    | 128-dim deterministic embedding vector                            |
| `performance_improvement`| FLOAT       | Measured speedup ratio                                            |
| `provenance`             | VARCHAR     | `measured` / `seeded` / `synthetic` / `unverified`               |
| `is_verified`            | BOOLEAN     | True iff benchmark confirmed the outcome                          |
| `verification_state`     | VARCHAR     | `verified_measured` / `synthetic` / `unverified`                 |
| `created_at`             | TIMESTAMPTZ | Memory creation timestamp                                         |

Indexes: `idx_memories_provenance`, `idx_memories_is_verified`, `idx_memories_verification_state`

---

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
pytest tests -q                           # 295 tests
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npx tsc --noEmit                          # TypeScript strict check
npm run dev                               # Dev server (proxies /api → localhost:8000)
npm run build                             # Production build
```

### Environment Variables

| Variable          | Required | Description                                |
|-------------------|----------|--------------------------------------------|
| `GROQ_API_KEY`    | Yes      | Groq API key for LLM reasoning             |
| `DATABASE_URL`    | Yes      | PostgreSQL connection string               |
| `VITE_API_BASE_URL` | No     | Frontend API base (default: `/api/v1`)     |

---

## Testing

```bash
# Backend: 295 tests, 0 failures
pytest backend/tests -q

# Phase 8 research integrity: 31/31 passed
python research/scratch/phase8_consistency_check.py

# Frontend TypeScript strict check
cd frontend && npx tsc --noEmit
```

---

## Known MVP Limitations

1. **Single PostgreSQL instance** — Multi-tenant support is not yet implemented.
2. **Index-only remediation** — Stage 7 creates B-tree indexes; GIN, BRIN, partial indexes require manual DDL.
3. **No automatic rollback** — If a created index degrades performance, AutoDBA reports it but does not automatically `DROP INDEX`.
4. **Frontend bundle size** — Vite bundle is ~692 KB ungzipped (~196 KB gzipped); code-splitting not yet applied.
5. **Groq rate limits** — Free-tier accounts are subject to RPM limits under heavy load.
6. **HypoPG availability** — Must be installed in the monitored PostgreSQL instance; if unavailable, counterfactual estimation is skipped with a warning.

---

## Architecture Decision Records

**Why deterministic bottleneck detection?**
EXPLAIN plan analysis is fully deterministic — the same query always produces the same bottleneck classification, eliminating LLM hallucination from the critical path.

**Why HypoPG before human approval?**
HypoPG estimates the planner's actual cost reduction for a hypothetical index without touching real data, preventing approval of indexes that wouldn't help.

**Why 10-run benchmarks?**
Statistical noise in single-run measurements is too high. 10 execution rounds with 2 warmup rounds gives a stable median and removes JIT/cache warm-up bias.

**Why cosine similarity RAG?**
Deterministic hash-based embeddings + cosine similarity retrieval requires zero external embedding API calls, ensuring offline/airgap deployability.

---

## Project Structure

```
AUTODBA/
├── backend/
│   ├── app/
│   │   ├── main.py                      # FastAPI app entry point
│   │   ├── api/v1/                      # Route handlers
│   │   ├── services/
│   │   │   ├── intelligence_service.py  # 10-stage pipeline orchestrator
│   │   │   ├── memory_service.py        # RAG + memory CRUD + provenance
│   │   │   ├── hypopg_service.py        # HypoPG counterfactual simulation
│   │   │   ├── benchmark_service.py     # Stage 8 runtime benchmarking
│   │   │   ├── safety_service.py        # DDL risk classification
│   │   │   └── approval_service.py      # Human approval gate
│   │   └── schemas/
│   │       └── optimization.py          # Pydantic models + provenance types
│   └── tests/                           # 295 backend tests
├── frontend/
│   ├── src/
│   │   ├── views/                       # Dashboard, Investigate, Approvals, etc.
│   │   ├── components/                  # CandidateEvaluationsCard, RAGHistoricalCases
│   │   ├── services/api.ts              # Backend API client
│   │   └── types/api.ts                 # TypeScript types (provenance, verification)
│   └── vite.config.ts
├── postgres/
│   └── init.sql                         # Schema + pg_stat_statements + HypoPG setup
├── research/                            # Phase 1–8 research artifacts (frozen)
├── docker-compose.yml
└── README.md
```

---

## License

MIT — see [LICENSE](LICENSE).
