-- 2026-05-19: mapped_history.trade TEXT 컬럼 신설
-- 의도: AgentTaskItem.trade (한글 공종, FE 의도) 의 BE source.
-- 현재 mapped_history.l6_main 은 WBS 매핑 후 카테고리 (예: "철근콘크리트공사") — Activity.trade
-- (예: "철근공사") 와 의미 다름. 사용자 "억지 매핑 금지" feedback 정합 위해 trade 컬럼 분리.
-- 참조: data-contract/INDEX.md D-16, data-contract/gaps.md §G.2.
-- 호출자: pipeline/agents/atomizer.py:130 mh_rows 생성 시 Activity.trade (state.py:30) 박기.

BEGIN;
ALTER TABLE mapped_history
  ADD COLUMN IF NOT EXISTS trade TEXT;
COMMIT;
