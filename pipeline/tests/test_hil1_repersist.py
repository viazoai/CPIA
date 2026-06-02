"""hil_1_node -- resume 후 mapper_activities 재persist (C5-2).

_apply_corrections 직후 corrected mapped 로 insert_mapper_activities_batch 재호출
-> DB requires_review=False + wa/l6/source upsert. Spec §5.1 #2.
PGClient 를 패치해 실 PG 없이 insert 호출 인자만 결정론적으로 검증.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.state import Activity


def _activity(idx: int, requires_review: bool) -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": "철근콘크리트공사",
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": f"company_{idx}",
        "unit": "m3",
        "today_qty": 10.0,
        "work_content": f"work_{idx}",
        "conditions": ["맑음"],
        "assigned_workers": 5.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "OLD",
        "mapping_conf": 0.5,
        "mapping_source": "hil_required",
        "requires_review": requires_review,
    }


def test_hil1_resume_repersists_mapper_activities() -> None:
    import pipeline.graph as graph_module
    from pipeline.graph import hil_1_node

    run_id = str(uuid.uuid4())
    mapped = [_activity(0, True), _activity(1, True)]
    state = {"mapped": mapped, "run_id": run_id, "date": "2025-09-25"}

    cfg = MagicMock()
    cfg.mapper.postgres_url = "postgresql://t:t@localhost:5432/t"

    fake_pg = MagicMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    fake_pg.insert_mapping_correction = AsyncMock()
    fake_pg.insert_mapper_activities_batch = AsyncMock()

    # api.py 가 항상 truthy 래퍼 {"corrections": {...}} 로 resume 하므로
    # graph.py:300-301 에서 언랩: corrections_raw["corrections"] or {}
    resume_payload = {"corrections": {"0": {"wa": "CORRECTED", "l6_main": "철근콘크리트공사"}}}

    with (
        patch.object(graph_module, "PGClient", return_value=fake_pg),
        patch.object(graph_module, "interrupt", return_value=resume_payload),
    ):
        result = asyncio.run(hil_1_node(state, cfg=cfg))

    # C5-2 핵심: insert_mapper_activities_batch 가 1회 awaited 돼야 함
    fake_pg.insert_mapper_activities_batch.assert_awaited_once()
    call = fake_pg.insert_mapper_activities_batch.await_args
    passed = call.kwargs.get("activities") if call.kwargs.get("activities") is not None else call.args[2]

    # 전건 requires_review=False (DB hil_pending 해소)
    assert all(a["requires_review"] is False for a in passed)

    # idx 0 — 사용자 정정 wa
    assert passed[0]["wa"] == "CORRECTED"
    assert passed[0]["mapping_source"] == "user_corrected"

    # idx 1 — corrections 에 없음: wa 유지, 수용 처리
    assert passed[1]["wa"] == "OLD"
    assert passed[1]["mapping_source"] == "user_corrected"
    assert passed[1]["requires_review"] is False

    # return 값도 corrected mapped
    assert all(a["requires_review"] is False for a in result["mapped"])
