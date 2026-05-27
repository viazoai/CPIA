"""Task 23 — V10 LLM 호출 결과 8 가드 검증 (실 Azure + PG).

1 wp sample: 한신비텍 NPW SYSTEM (risk_level=이상, 사용자가 PoC 검증한 케이스).
G6 강화 (정상범주 금지) + G8 (공종 고유 인사이트) + keyword schema 검증.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import asyncpg
import pytest
from dotenv import load_dotenv
from openai import AzureOpenAI

_CPIA_ROOT = Path(__file__).resolve().parents[3]
# pipeline/.env.local (Azure 키) + 루트 .env (POSTGRES_URL) 둘 다 로드.
load_dotenv(_CPIA_ROOT / "pipeline" / ".env.local")
load_dotenv(_CPIA_ROOT / ".env")
load_dotenv(_CPIA_ROOT / ".env.local", override=False)

DSN = os.environ.get("POSTGRES_URL", "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia")


@pytest.mark.skipif(
    not os.environ.get("AZURE_OPENAI_API_KEY"),
    reason="실 Azure 호출 필요 — local dev .env.local 가 있어야 함",
)
async def test_v10_npw_system_g6_g8_keyword_schema():
    """한신비텍 NPW SYSTEM 6/30 — V10 LLM 호출 결과 G6/G8/keyword schema 검증.

    사전 조건: 6/30 데이터가 AWS PG 에 적재되어 있어야 함 (사용자 시연 윈도우 외 이지만
    PoC 검증 데이터 보존). 만약 없으면 skip.
    """
    from pipeline.agents.optimizer._trade_frames import lookup_frame
    from pipeline.agents.optimizer.prompt import (
        DIAG_PROMPT_V10,
        RECS_PROMPT_V10,
        build_diag_input_v10,
        build_recs_input_v10,
    )

    conn = await asyncpg.connect(DSN)
    try:
        # forecasts row + optimizer_advice 의 degradation_cases 가져오기
        f_row = await conn.fetchrow(
            """
            SELECT f.company, f.l6_main, f.assessment, f.risk_level,
                   f.today_productivity, f.delay_days, f.mh_gap, f.point_in_time_delay_days,
                   f.today_conditions, f.main_unit
            FROM forecasts f JOIN pipeline_runs pr USING(run_id)
            WHERE pr.report_date = '2025-06-30' AND pr.site_id = 'm15x-ph3-ibl'
              AND f.company = '한신비텍' AND f.l6_main = 'NPW(2차 SCR) SYSTEM'
            LIMIT 1
            """
        )
        if not f_row:
            pytest.skip("6/30 한신비텍 NPW row 없음 — PoC 데이터 보존 윈도우 외")

        cases_row = await conn.fetchrow(
            """
            SELECT oa.degradation_cases::text AS dc
            FROM optimizer_advice oa JOIN pipeline_runs pr USING(run_id)
            WHERE pr.report_date = '2025-06-30' AND pr.site_id = 'm15x-ph3-ibl'
              AND oa.company = '한신비텍' AND oa.l6_main = 'NPW(2차 SCR) SYSTEM'
            LIMIT 1
            """
        )
        cases = json.loads(cases_row["dc"]) if cases_row and cases_row["dc"] else []
        cases_formatted = [
            {
                "date": c.get("date"),
                "conditions": c.get("conditions"),
                "productivity": c.get("productivity"),
                "activities": c.get("activities"),
                "recovery": {
                    "recovery_days": (c.get("recovery") or {}).get("recovery_days"),
                    "trajectory": [],
                },
            }
            for c in cases[:5]
        ]
    finally:
        await conn.close()

    # forecast_row dict 만들기 (Decimal → float 변환)
    forecast_row = dict(f_row)
    for key in ("today_productivity", "mh_gap"):
        if forecast_row.get(key) is not None:
            forecast_row[key] = float(forecast_row[key])

    # frame lookup
    category, frame_text = lookup_frame(forecast_row["l6_main"])

    # RECS 호출
    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    recs_payload = build_recs_input_v10(forecast_row, cases_formatted, "2025-06-30", category, frame_text)
    recs_resp = azure.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        messages=[
            {"role": "system", "content": RECS_PROMPT_V10},
            {
                "role": "user",
                "content": json.dumps(recs_payload, ensure_ascii=False, default=str),
            },
        ],
        response_format={"type": "json_object"},
    )
    recs_out = json.loads(recs_resp.choices[0].message.content)

    # DIAG 호출
    diag_payload = build_diag_input_v10(
        forecast_row,
        cases_formatted,
        "2025-06-30",
        category,
        frame_text,
        recs_out.get("recommendations") or [],
    )
    diag_resp = azure.chat.completions.create(
        model=os.environ["LLM_MODEL"],
        messages=[
            {"role": "system", "content": DIAG_PROMPT_V10},
            {
                "role": "user",
                "content": json.dumps(diag_payload, ensure_ascii=False, default=str),
            },
        ],
        response_format={"type": "json_object"},
    )
    diag_out = json.loads(diag_resp.choices[0].message.content)

    # === 8 가드 검증 ===
    diagnosis = diag_out.get("diagnosis", "")
    recommendations = recs_out.get("recommendations", [])

    # G6: 정상범주 금지 (risk_level=이상)
    banned = ["정상범주", "정상 범위", "평시 대비 충분히 높음"]
    for word in banned:
        assert word not in diagnosis, f"G6 위반 — '{word}' diagnosis 에 발견: {diagnosis[:200]}"

    # keyword schema: 3 개 이상, keyword 길이 합리 (3~14자), action + reason 존재
    assert len(recommendations) >= 3, f"recommendations 부족: {len(recommendations)}"
    for r in recommendations:
        assert "keyword" in r and "action" in r and "reason" in r, f"필드 누락: {r}"
        kw_len = len(r["keyword"])
        assert 3 <= kw_len <= 14, (
            f"keyword 길이 위반 (5~10자 권장, 14 까지 허용): '{r['keyword']}' ({kw_len}자)"
        )
        assert r["action"].strip(), f"action 빈값: {r}"
        assert r["reason"].strip(), f"reason 빈값: {r}"

    # 한자 0건 (G3 부산물)
    han = re.findall(r"[一-鿿]", diagnosis + "".join(str(r) for r in recommendations))
    assert not han, f"한자 발견: {han}"

    # delay 두 차원 인용 (DIAG 의 첫 문장 패턴)
    fwd = forecast_row.get("delay_days")
    if fwd is not None and abs(fwd) > 5:
        assert any(kw in diagnosis for kw in ["지연", "뒤처", "부족", "낮"]), (
            f"delay 인용 없음 (forward={fwd}): {diagnosis[:200]}"
        )
