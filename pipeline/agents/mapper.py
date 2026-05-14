"""Mapper agent — 작업일보 → WBS 매핑.

Spec: docs/schema/mapping-layer.md §3 (6단계 흐름) + §4 (WA 결정 4단계).

Task 6 (이 파일) — helper 함수 (build_embedding_input / build_llm_input /
build_bp_context / resolve_wa).
Task 7 — map_activity 통합 함수.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pipeline.state import Activity, BPSummary, ParsedDailyReport


# 시트2 직종 noise 제거 — mapping-layer.md §2.1 (3)
_TRADE_KEYWORDS = (
    "형틀",
    "철근",
    "콘크리트",
    "타설",
    "조적",
    "방수",
    "도장",
    "비계",
    "용접",
    "배관",
    "전기공",
    "덕트",
    "단열",
    "내장",
    "타일",
    "미장",
    "양생",
    "철골",
    "보온",
    "케이블",
)
_MGR_KEYWORDS = (
    "소장",
    "관리자",
    "감독",
    "감리",
    "안전",
    "Shop",
    "BIM",
    "공무",
    "설계",
    "품질",
    "운영",
    "창고",
)
_NOISE_KEYWORDS = ("기능공 투입 Total", "기능공 투입 total")


def _is_trade_job(job: str) -> bool:
    """시트2 직종 noise 제거."""
    if any(n in job for n in _NOISE_KEYWORDS):
        return False
    if any(m in job for m in _MGR_KEYWORDS):
        return False
    return any(k in job for k in _TRADE_KEYWORDS)


@dataclass(frozen=True)
class WAResolution:
    """WA 결정 결과."""

    value: str | None
    source: Literal[
        "auto_bp_single",
        "auto_l6_single",
        "auto_sheet1_text",
        "hil_required",
    ]


def build_embedding_input(activity: Activity) -> str:
    """임베딩 input — 작업line 자체만 (mapping-layer.md §3.1).

    숫자·BP 컨텍스트 제외. v2 의 숫자 오염 (배관공 165168 등) 방지.
    """
    return (
        f"회사: {activity['company']}\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}\n"
        f"공종: {activity['trade']}"
    )


def build_bp_context(
    company: str,
    parsed_report: ParsedDailyReport | None,
) -> str:
    """LLM input 용 BP사 단위 풍부 컨텍스트 (시트1+2+3 join)."""
    if not parsed_report:
        return "  · (parsed_report 미제공 — BP 컨텍스트 없이 진행)"

    summaries: list[BPSummary] = [s for s in parsed_report["bp_summaries"] if s["company"] == company]
    work_texts = [s["work_text_today"] for s in summaries if s["work_text_today"]]
    today_incr = sum(s["today_incr_total"] for s in summaries)
    today_cum = sum(s["today_cum_total"] for s in summaries)
    work_text_str = " / ".join(t for t in work_texts[:2] if t)[:200] if work_texts else "미기재"

    sheet1_block = (
        f"  · [시트1] 주요작업 텍스트 (BP사 기재): {work_text_str}\n"
        f"  · [시트1] 금일 신규 투입 인원 (Incr.): {today_incr:,}명\n"
        f"  · [시트1] 금일 누적 인원 (Cum.): {today_cum:,}명-일"
    )

    # 시트2 — 기능공만, noise 제거
    jobs: dict[str, int] = {}
    for j in parsed_report["job_allocations"]:
        if j["company"] != company:
            continue
        if not _is_trade_job(j["job_type"]):
            continue
        jobs[j["job_type"]] = jobs.get(j["job_type"], 0) + j["workers_cum_t"]
    if jobs:
        top_jobs = sorted(jobs.items(), key=lambda x: -x[1])[:8]
        job_lines = "\n".join(f"      - {j}: {c:,}명-일" for j, c in top_jobs)
        sheet2_block = "  · [시트2] 기능공 직종 (금일누계 Cum.T):\n" + job_lines
    else:
        sheet2_block = "  · [시트2] 기능공 직종: 미신고"

    # 시트3 — 장비
    eqs = [e for e in parsed_report["equipment_allocations"] if e["company"] == company]
    if eqs:
        top_eq = sorted(eqs, key=lambda e: -e["count_cum_t"])[:5]
        eq_lines = "\n".join(
            f"      - {e['equipment_big']}/{e['equipment_mid']} "
            f"({e['equipment_spec'] or '규격 미상'}): {e['count_cum_t']:,}회-일"
            for e in top_eq
        )
        sheet3_block = "  · [시트3] 투입 장비 (금일투입누계 Cum.T):\n" + eq_lines
    else:
        sheet3_block = "  · [시트3] 투입 장비: 미신고"

    return f"{sheet1_block}\n{sheet2_block}\n{sheet3_block}"


def build_llm_input(
    activity: Activity,
    parsed_report: ParsedDailyReport | None,
) -> str:
    """LLM input — 작업line + BP사 단위 풍부 컨텍스트 (mapping-layer.md §3.1)."""
    bp_ctx = build_bp_context(activity["company"], parsed_report)
    today_str = activity["today_qty"] if activity["today_qty"] not in (None, 0) else "-"
    plan_str = activity["plan_total_qty"] if activity["plan_total_qty"] not in (None, 0) else "-"
    return (
        f"회사: {activity['company']} (공종 {activity['trade']})\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}  |  금일실적: {today_str}  |  계획 총수량: {plan_str}\n"
        f"[BP사 단위 컨텍스트]\n{bp_ctx}"
    )


def resolve_wa(
    activity: Activity,
    l6_choice: str,
    cand_pool: list[tuple[str, str]],
    parsed_report: ParsedDailyReport | None,
) -> WAResolution:
    """WA 결정 4단계 (mapping-layer.md §4)."""
    # 1단계 — BP scope WA 단일
    bp_wa = {wa for wa, _ in cand_pool}
    if len(bp_wa) == 1:
        return WAResolution(value=next(iter(bp_wa)), source="auto_bp_single")

    # 2단계 — L6 결정 후 그 L6 의 WA 단일
    l6_wa = {wa for wa, l6 in cand_pool if l6 == l6_choice}
    if len(l6_wa) == 1:
        return WAResolution(value=next(iter(l6_wa)), source="auto_l6_single")

    # 3단계 — 시트1 자연어 LLM 추론 (PoC 비활성, GATE 2 활성)
    # TODO: GATE 2 진입 시 llm_infer_wa() 추가

    # 4단계 — H-i-L 강제
    return WAResolution(value=None, source="hil_required")
