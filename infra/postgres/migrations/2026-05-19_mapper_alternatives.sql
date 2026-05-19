-- G23 — mapper_activities.alternatives jsonb 컬럼 추가.
-- mapper_node 의 RAG top-K (K=3) 후보 + score 적재. review 페이지의 대안 WP 후보 dropdown.

BEGIN;

ALTER TABLE mapper_activities
    ADD COLUMN IF NOT EXISTS alternatives JSONB DEFAULT '[]'::jsonb NOT NULL;

COMMENT ON COLUMN mapper_activities.alternatives IS
  'RAG top-K candidates as [{wa, l6_main, score}, ...]. Sorted by score DESC. K=3 default.';

CREATE INDEX IF NOT EXISTS mapper_activities_alternatives_gin
    ON mapper_activities USING GIN (alternatives);

COMMIT;
