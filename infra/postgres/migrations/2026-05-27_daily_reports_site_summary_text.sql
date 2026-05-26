-- daily_reports.site_summary_text — Optimizer LLM 산출 site 수준 narrative
--
-- 배경:
--   commit 21c10f7 (2026-05-22, feat(site-summary)) 가 runtime 에서 ALTER TABLE 만 치고
--   migration sql 파일을 안 만듦. 운영 DB 에는 컬럼이 존재하지만 fresh DB rebuild 시
--   (예: AWS 마이그 후 init.sql + migrations 만으로 schema 복원) UndefinedColumnError 발생.
--   본 migration 으로 idempotent 하게 컬럼 등록.
--
-- 채우는 곳 (writer):
--   - scripts/backfill_daily_report_views_v2.py:165 — `--with-summary` 플래그 UPDATE
--   - scripts/backfill_optimizer_advice_llm.py:272 — 같이 호출 시 채움
--   - pipeline/agents/optimizer/site_summary.py — generate_site_summary() Azure JSON LLM
--   - (★ 미연결 #N20) pipeline/agents/optimizer/agent.py optimize() live cycle 에는 아직 없음
--
-- 읽는 곳 (reader):
--   - web/app/api/mock/report/[date]/route.ts:24 — SELECT dr.site_summary_text
--   - web/app/(app)/reports/page.tsx:269 — aiSummaryText={detail.site_summary_text}
--   - web/app/components/charts/ForecastChart.tsx:376 — narrative 박스 (NULL 시 룰베이스 fallback)

BEGIN;

ALTER TABLE daily_reports
    ADD COLUMN IF NOT EXISTS site_summary_text TEXT;

COMMENT ON COLUMN daily_reports.site_summary_text IS
    'Optimizer LLM (Azure gpt-5.1-chat-ai-board-test, JSON response_format) 산출 site 수준 narrative. 1~2 단락 200~300자 경영진 친화 요약. NULL 이면 FE (ForecastChart) 가 룰베이스 fallback. 채움 경로: backfill_v2 --with-summary 또는 backfill_optimizer_advice_llm. 이슈 #N20: live optimize() 미연결.';

COMMIT;
