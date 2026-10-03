-- Phase 2: Additive Migration for Optimization Memory Provenance & Verification
-- Safe, idempotent additive migration for existing databases and init sequences

ALTER TABLE optimization_memories
    ADD COLUMN IF NOT EXISTS provenance VARCHAR(50) NOT NULL DEFAULT 'unverified',
    ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS verification_state VARCHAR(50) NOT NULL DEFAULT 'unverified';

CREATE INDEX IF NOT EXISTS idx_optimization_memories_provenance
    ON optimization_memories (provenance);

CREATE INDEX IF NOT EXISTS idx_optimization_memories_is_verified
    ON optimization_memories (is_verified);
