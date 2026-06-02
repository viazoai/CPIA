-- 2026-06-02: B3 진행도 per-item 실시간 — agent_progress 신설
-- 참조: spec 2026-06-02-cpia-0925-demo-refinement-design.md §6.1
-- 노드별 upsert_agent_progress(db.py) 가 (run_id, agent) UPSERT.
-- run_id 는 FK 미설정 (fire-and-forget progress write 가 FK 로 막히면 안 됨).

CREATE TABLE IF NOT EXISTS agent_progress (
  run_id     UUID        NOT NULL,
  agent      TEXT        NOT NULL,   -- 'parser'|'mapper'|'atomizer'|'exporter'|'forecaster'|'optimizer'
  processed  INTEGER     NOT NULL DEFAULT 0,
  total      INTEGER     NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, agent)
);

CREATE INDEX IF NOT EXISTS idx_agent_progress_run
  ON agent_progress (run_id);

COMMENT ON TABLE agent_progress IS
  'B3 진행도 per-(run,agent) 카운터. upsert_agent_progress 가 GREATEST 로 단조 보장. 본 cycle 2026-06-02.';
