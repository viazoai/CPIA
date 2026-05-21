-- Phase 1 (2026-05-21): 데이터 정합화 — embedding cache + merge log.
-- Dependency contract:
--   prototype_embedding_cache  -> Task 5 (L7.5 임베딩) 전제
--   mapped_history_merge_log   -> Task 4 (mapped_history UNIQUE 합산) 전제
-- 재실행 안전 (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS prototype_embedding_cache (
  text_hash text PRIMARY KEY,
  source_text text NOT NULL,
  embedding float8[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_embedding_cache_created
  ON prototype_embedding_cache(created_at);

CREATE TABLE IF NOT EXISTS mapped_history_merge_log (
  id bigserial PRIMARY KEY,
  src_id bigint NOT NULL,
  tgt_id bigint NOT NULL,
  run_id uuid NOT NULL,
  report_date date NOT NULL,
  site_id text NOT NULL,
  wa text,
  l6_main text,
  old_company text NOT NULL,
  new_company text NOT NULL,
  merged_today_qty numeric,
  merged_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_merge_log_date
  ON mapped_history_merge_log(report_date DESC);
