"""_build_optimizer_view 단위 테스트 — pure function."""

from __future__ import annotations

from pipeline.agents.optimizer.view_builder import _build_optimizer_view


def test_optimizer_view_세보엠이씨_4섹션_6칸():
    """세보 케이스 — 진단/유사/권고/상세 4 섹션 + 6칸 details."""
    advice = [
        {
            "company": "세보엠이씨",
            "l6_main": "기계소화설비",
            "diagnosis": "오늘 생산성은 정상 범위 (CPI 51.3)",
            "degradation_cases": [
                {
                    "date": "2025-09-23",
                    "activities": ["철근 조립"],
                    "conditions": "흐림",
                    "productivity": 25.2,
                    "recovery": {"recovery_days": 1},
                }
            ],
            "recommendations": [
                {"rank": 1, "text": "장비 점검 우선 진행"},
                {"rank": 2, "text": "야간 추가 인력 확보"},
            ],
            "recovery_distribution": {"d+1": 2, "not_recovered": 1},
            "recovery_pattern": [
                {"date": "2025-09-23", "recovery_days": 1},
                {"date": "2025-09-25", "recovery_days": 2},
            ],
        }
    ]
    forecast = [
        {
            "company": "세보엠이씨",
            "l6_main": "기계소화설비",
            "wa": "FAB",
            "risk_level": "정상",
            "delay_days": -13,
        }
    ]

    v = _build_optimizer_view(advice, forecast, [])
    assert v["default_wp_id"] is not None
    wp = v["by_wp"][v["default_wp_id"]]
    assert wp["diagnosis"].startswith("오늘")
    assert len(wp["similar_cases"]) == 1
    assert wp["similar_cases"][0]["outcome"] == "1일 후 회복"
    assert wp["recommendations"] == ["장비 점검 우선 진행", "야간 추가 인력 확보"]
    assert len(wp["details"]) == 6
    labels = [d["label"] for d in wp["details"]]
    assert labels == ["위험 평가", "진단 대상", "유사 사례 수", "평균 회복 일수", "회복 분포", "일정 영향"]
    avg_rd_detail = next(d for d in wp["details"] if d["label"] == "평균 회복 일수")
    assert avg_rd_detail["value"] == "1.5일"


def test_optimizer_view_skips_advice_without_forecast_match():
    """forecast 에 매칭 안되는 advice 는 by_wp 에서 skip."""
    advice = [{"company": "회사X", "l6_main": "L6X", "diagnosis": "..."}]
    forecast = [{"company": "회사Y", "l6_main": "L6Y", "wa": "FAB"}]
    v = _build_optimizer_view(advice, forecast, [])
    assert v["by_wp"] == {}
    assert v["default_wp_id"] is None


def test_optimizer_view_handles_missing_recovery():
    """recovery 가 빈 dict 면 outcome=미회복."""
    advice = [
        {
            "company": "세보",
            "l6_main": "L6",
            "diagnosis": "",
            "degradation_cases": [{"date": "2025-09-01", "productivity": 30, "recovery": {}}],
            "recommendations": [],
            "recovery_pattern": [],
        }
    ]
    forecast = [{"company": "세보", "l6_main": "L6", "wa": "FAB"}]
    v = _build_optimizer_view(advice, forecast, [])
    wp = v["by_wp"][v["default_wp_id"]]
    assert wp["similar_cases"][0]["outcome"] == "미회복"
    # avg_rd 없으면 "—"
    avg_rd_detail = next(d for d in wp["details"] if d["label"] == "평균 회복 일수")
    assert avg_rd_detail["value"] == "—"


def test_optimizer_view_recommendation_string_format():
    """recommendations 가 str list 일 때도 정상 처리."""
    advice = [
        {
            "company": "세보",
            "l6_main": "L6",
            "diagnosis": "",
            "recommendations": ["권고 1", "권고 2"],
        }
    ]
    forecast = [{"company": "세보", "l6_main": "L6", "wa": "FAB"}]
    v = _build_optimizer_view(advice, forecast, [])
    wp = v["by_wp"][v["default_wp_id"]]
    assert wp["recommendations"] == ["권고 1", "권고 2"]
