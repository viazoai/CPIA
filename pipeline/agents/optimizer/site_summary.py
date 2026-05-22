"""Site 수준 진척 요약 LLM 산출 — 경영진 1~2단락 narrative.

view_builder.build 산출 결과 (kpi, scenarios, wp_summary, optimizer_view) 를
받아 1~2단락 자연어 요약을 만들어 daily_reports.site_summary_text 에 적재.

설계:
- Optimizer agent.py 의 _call_azure_llm 패턴과 동일 (Azure OpenAI gpt-5.1 + JSON)
- 입력: 결정론적 dict (산출된 숫자 + top 3 risk wp 의 LLM diagnosis/recommendations)
- 출력: {"summary": "..."} JSON. 실패 시 fallback text (None X).
- fail-fast — 호출자가 try/except 처리.

호출 지점:
- view_builder.build 끝 + backfill 스크립트 (1줄 추가, 다른 세션 코드 무관)
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from openai import AzureOpenAI


SYSTEM_PROMPT = """당신은 건설 현장의 진척 상황을 경영진에게 보고하는 분석가입니다.

입력 JSON 데이터를 받아 현재 진척 상황과 AI 권고 적용 시 만회 가능성을
1~2 단락 (총 200~300자) 의 한국어 경영진 문체로 자연스럽게 정리하세요.

출력 형식 (반드시 JSON):
{"summary": "..."}

작성 원칙:
- 숫자는 입력값 그대로 인용 (소수점 1자리 이내).
- 1단락: 오늘 진척 상황 — "기준일 시점 진척률 X% 로 계획 (Y%) 대비 Z%p 뒤처짐.
  이대로 가면 D+N 일 지연 완공 예상." 형식.
- 2단락: AI 권고 적용 시 효과 — "위험 공종 A, B, C 의 [핵심 권고 액션] 시 N일 만에
  계획 따라잡고 동일 완공일 유지 가능." 형식.
- 위험 공종은 입력 top_risk_wps 에서 1~3개만 자연스럽게 언급.
- 통계 용어 (P25/P50/P75, MH 가중, EVM 등) 사용 금지. 경영진 자연어만.
- 추측/과장/입력에 없는 사실 추가 금지.
- 한자 사용 금지 — 한글 또는 영어 고유명사만.
"""


def build_site_summary_payload(
    *,
    report_date: str,
    site_id: str,
    kpi: dict[str, Any],
    scenarios: dict[str, Any],
    wp_summary: list[dict[str, Any]],
    optimizer_view: dict[str, Any],
    s_curve: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 입력 payload 결정론적으로 build.

    - 진척률 (planned/actual) = s_curve 의 report_date 시점 값
    - delay_days, recovery_days = kpi
    - top_risk_wps = wp_summary impact desc top 3 → optimizer_view.by_wp 에서 LLM diagnosis + 첫 recommendation
    - no_action_ec, base_p50_ec = scenarios.site
    """
    today_point = next((p for p in s_curve if p.get("date") == report_date), None)
    planned_pct = float(today_point.get("planned") if today_point else 0)
    actual_pct = float(today_point.get("actual") if today_point else 0)

    site = scenarios.get("site") or {}
    no_action = site.get("no_action") or {}
    base_p50 = site.get("base_p50") or {}

    by_wp = (optimizer_view or {}).get("by_wp") or {}
    top = sorted(
        [w for w in (wp_summary or []) if (w.get("impact") or 0) > 0],
        key=lambda w: w.get("impact") or 0,
        reverse=True,
    )[:3]
    top_risk_wps: list[dict[str, Any]] = []
    for w in top:
        o = by_wp.get(w.get("wp_id")) or {}
        diag = o.get("diagnosis")
        if not diag or diag == "cold_start":
            diag = None
        recs_raw = o.get("recommendations") or []
        recs: list[str] = []
        for r in recs_raw:
            if isinstance(r, dict):
                t = r.get("text") or ""
            else:
                t = str(r)
            if t:
                recs.append(t)
        top_risk_wps.append(
            {
                "wp_name": w.get("wp_name"),
                "trade": w.get("trade"),
                "diagnosis": diag,
                "top_recommendation": recs[0] if recs else None,
            }
        )

    return {
        "report_date": report_date,
        "site_id": site_id,
        "progress_pct": {"planned": round(planned_pct, 1), "actual": round(actual_pct, 1)},
        "gap_pct": round(planned_pct - actual_pct, 1),
        "delay_days": int(kpi.get("delay_days") or 0),
        "ai_recovery_days": int(base_p50.get("recovery_days") or 0),
        "expected_completion": {
            "if_no_action": no_action.get("expected_completion"),
            "ai_scenario": base_p50.get("expected_completion"),
            "plan": kpi.get("expected_completion"),
        },
        "top_risk_wps": top_risk_wps,
    }


def generate_site_summary(
    payload: dict[str, Any],
    *,
    azure: Optional[AzureOpenAI] = None,
    model: Optional[str] = None,
) -> str:
    """LLM 호출 → summary text 반환. fail-fast (예외 그대로 raise)."""
    if azure is None:
        azure = AzureOpenAI(
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        )
    model = model or os.environ.get("LLM_MODEL", "gpt-5.1-chat-ai-board-test")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
    resp = azure.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
    )
    parsed = json.loads(resp.choices[0].message.content)
    return str(parsed.get("summary", "")).strip()
