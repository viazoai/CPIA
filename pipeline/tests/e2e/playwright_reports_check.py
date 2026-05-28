"""Task 25 — Playwright reports 페이지 자동 검증 (Phase 8 용).

Phase 8 의 Task 27-29 가 각 월 backfill 후 호출. Playwright MCP 또는 직접
playwright 사용. dev server (port 5536) 떠 있어야 함.

본 파일은 skeleton — Task 27-29 시점에 사용자가 dev server 띄우고 실 검증.
"""

from __future__ import annotations


async def check_reports_page(date_str: str, base_url: str = "http://localhost:5536"):
    """reports 페이지 자동 스냅샷 + UI 가드 검증.

    검증 항목 (Task 25 spec):
    - KpiStrip / GapKpiCard / QuadrantCountKpi 모두 값 (no "—")
    - 분포도 wp 모두 trade ∈ {건축, 토목}
    - wp 클릭 → OptimizerResult [keyword] action / 이유 표시
    - 진단 G6 금지 단어 0건
    - ForecastChart aiAdvice 박스 "−N일 만회" badge
    - similar_cases 3건
    """
    # Implementation: Playwright MCP 사용 — Phase 8 시점에 별도 작성
    raise NotImplementedError("Phase 8 시점에 dev server + Playwright MCP 로 호출")
