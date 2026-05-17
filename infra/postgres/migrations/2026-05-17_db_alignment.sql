-- 2026-05-17 — sites +4 컬럼 (B_Track Dashboard Layer 1 카드)
-- Spec: docs/superpowers/specs/2026-05-17-cpia-db-migration-api-contract-design.md §5
-- 멱등 (IF NOT EXISTS) — 두 번 돌려도 무방

BEGIN;
ALTER TABLE sites
  ADD COLUMN IF NOT EXISTS location    TEXT,
  ADD COLUMN IF NOT EXISTS headcount   INT,
  ADD COLUMN IF NOT EXISTS hours_saved NUMERIC,
  ADD COLUMN IF NOT EXISTS fte_saved   NUMERIC;
COMMIT;
