-- 2026-06-10 (A+C): optimizer_advice.briefing — 경영진 구두 브리핑 한 단락.
-- "리스크 및 대안 검토" 진단을 룰베이스 문장 대신 LLM 종합 브리핑으로 (BRIEFING_PROMPT).
-- view_builder._build_optimizer_view 가 advice.briefing → by_wp.briefing 으로 forward.
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS briefing TEXT;
-- 2026-06-11: 헤드라인 한 줄 (볼드 상단) — 브리핑 문단 위에 한 줄 요약.
ALTER TABLE optimizer_advice ADD COLUMN IF NOT EXISTS briefing_headline TEXT;
