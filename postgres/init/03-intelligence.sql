-- Phase 4.1: Intelligence Memory
-- Stores historical AutoDBA optimization outcomes and their embeddings.

CREATE TABLE IF NOT EXISTS optimization_memories (
    id BIGSERIAL PRIMARY KEY,

    incident_type VARCHAR(100) NOT NULL,
    query_fingerprint VARCHAR(255),
    query_text TEXT NOT NULL,

    diagnosis JSONB NOT NULL,
    recommendation JSONB NOT NULL,
    validation JSONB,
    benchmark JSONB,

    outcome VARCHAR(50) NOT NULL,
    outcome_summary TEXT,

    embedding JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_optimization_memories_incident_type
    ON optimization_memories (incident_type);

CREATE INDEX IF NOT EXISTS idx_optimization_memories_outcome
    ON optimization_memories (outcome);

CREATE INDEX IF NOT EXISTS idx_optimization_memories_created_at
    ON optimization_memories (created_at DESC);