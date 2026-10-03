# Phase 5C: Live Research Database Readiness Report

**Repository**: `C:\Users\swarsh\Desktop\autodba-research`  
**Branch**: `research/outcome-aware-ranking`  
**Baseline Directory**: `C:\Users\swarsh\Desktop\autodba-main` (Pristine and untouched)  
**Current Checkpoint Commit**: `4b7a616` (`phase5c: document research database readiness blocker`)
**Scope**: Live verification of the isolated PostgreSQL research container, extension availability, seed schema row counts, and baseline physical index state.

---

## 1. Final Verdict

# **A. READY FOR FIRST PILOT**

The isolated research PostgreSQL container is running, healthy, and fully initialized with the complete seed dataset and required extensions. The physical index state is clean and verified against live PostgreSQL catalogs.

---

## 2. Container & Database Identity (Verified LIVE)

| Property | Verified Live Value | Confirmation Source |
|---|---|---|
| **Container Name** | `autodba-main-postgres-1` | `docker ps` |
| **Image** | `autodba-main-postgres:latest` | Built from `postgres/Dockerfile` on base `postgres:17` |
| **Container Status** | `Up (healthy)` | Docker healthcheck (`pg_isready -U autodba -d autodba`) |
| **Port Mapping** | `0.0.0.0:5432->5432/tcp` | Docker networking |
| **Storage Volume** | `autodba-main_pgdata` | Docker volume |
| **Current Database** | `autodba` | `SELECT current_database();` |
| **Current User** | `autodba` | `SELECT current_user;` |
| **PostgreSQL Version** | `PostgreSQL 17.11 (Debian 17.11-1.pgdg13+2) on x86_64-pc-linux-gnu` | `SELECT version();` |

---

## 3. Extension Availability & Usability (Verified LIVE)

| Extension | Version | Installed? | Usable? | Verification Detail |
|---|---|---|---|---|
| **`hypopg`** | `1.4.3` | **YES** | **YES** | `SELECT * FROM hypopg_reset();` executed successfully with 0 errors. |
| **`pg_stat_statements`** | `1.11` | **YES** | **YES** | Loaded via `shared_preload_libraries`, `track=all`, `SELECT count(*) FROM pg_stat_statements;` returned valid metrics. |
| **`plpgsql`** | `1.0` | **YES** | **YES** | Core procedural language active. |

---

## 4. Seed Schema & Row Counts (Verified LIVE vs Expected)

| Table | Expected Count (`02-seed.sql`) | Actual Verified Count (LIVE DB) | Status |
|---|---|---|---|
| **`customers`** | 500 | **500** | ✅ Exact match |
| **`products`** | 100 | **100** | ✅ Exact match |
| **`orders`** | 5,000 | **5,000** | ✅ Exact match |
| **`order_items`** | 15,000 | **15,000** | ✅ Exact match |
| **`optimization_memories`** | 0 | **0** | ✅ Clean baseline (0 rows) |

---

## 5. Baseline Physical Index State (Verified LIVE)

Inspection of `pg_indexes WHERE schemaname = 'public'` on the live database confirms the following physical indexes:

### Benchmark Tables
1. **`customers`**:
   - `customers_pkey`: `CREATE UNIQUE INDEX customers_pkey ON public.customers USING btree (id)`
   - `customers_email_key`: `CREATE UNIQUE INDEX customers_email_key ON public.customers USING btree (email)`
2. **`products`**:
   - `products_pkey`: `CREATE UNIQUE INDEX products_pkey ON public.products USING btree (id)`
   - `idx_products_category`: `CREATE INDEX idx_products_category ON public.products USING btree (category)`
3. **`orders`**:
   - `orders_pkey`: `CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)`
   - `idx_orders_order_date`: `CREATE INDEX idx_orders_order_date ON public.orders USING btree (order_date)`
   - **Critical Baseline Confirmation**: `orders(customer_id)` has **zero** physical indexes. Foreign key lookup queries on `customer_id` will execute pure Sequential Scans as required for the pilot baseline.
4. **`order_items`**:
   - `order_items_pkey`: `CREATE UNIQUE INDEX order_items_pkey ON public.order_items USING btree (id)`
   - `idx_order_items_order_id`: `CREATE INDEX idx_order_items_order_id ON public.order_items USING btree (order_id)`
   - `idx_order_items_product_id`: `CREATE INDEX idx_order_items_product_id ON public.order_items USING btree (product_id)`
5. **`optimization_memories`**:
   - `optimization_memories_pkey` (PRIMARY KEY)
   - `idx_optimization_memories_created_at`
   - `idx_optimization_memories_incident_type`
   - `idx_optimization_memories_is_verified`
   - `idx_optimization_memories_outcome`
   - `idx_optimization_memories_provenance`

### AutoDBA-Generated Index Verification
- Query: `SELECT tablename, indexname FROM pg_indexes WHERE indexname LIKE 'idx_autodba_%';`
- Result: **0 rows returned**.
- **Confirmation**: The database is in a completely clean pre-pilot state with no residual AutoDBA indexes.

---

## 6. Runner Target Configuration & Safety Guard Verification

- **Configured Target**: `POSTGRES_HOST=localhost` (or `postgres`), `POSTGRES_PORT=5432`, `POSTGRES_DB=autodba`, `POSTGRES_USER=autodba`.
- **Safety Whitelist**: `ALLOWED_RESEARCH_HOSTS = frozenset({"localhost", "127.0.0.1", "postgres", "test-db"})`.
- **Pre-Flight Guards in `MeasuredCaseRunner`**:
  1. Verifies connectivity to the live container on port 5432.
  2. Verifies `hypopg` and `pg_stat_statements` are usable.
  3. Verifies `customers`, `products`, `orders`, and `order_items` tables exist.
  4. Verifies no equivalent index exists on the target relation prior to candidate execution.
  5. Ownership-aware cleanup ensures only newly created indexes (`status == APPLIED`) are torn down.

---

## 7. Explicit Statements of Non-Execution

1. **Zero physical indexes were created or dropped** during this readiness validation.
2. **Zero measured cases were executed**.
3. **`MeasuredCaseRunner.execute_pilot_case()` was NOT called**.
4. **`ClosedLoopService.execute()` was NOT called**.
5. **Zero table data mutations occurred** (row counts remain exactly 500, 100, 5,000, 15,000).
6. **Zero production application files or research logic files were modified**.
7. **`C:\Users\swarsh\Desktop\autodba-main` remains 100% pristine and untouched**.
