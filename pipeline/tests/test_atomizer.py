"""Atomizer 테스트 — 6 unit (no I/O) + 5 integration (실 Azure + Chroma + PG)."""

from __future__ import annotations

import os
import uuid

import pytest

from pipeline.agents.atomizer import (
    AtomizerConfig,
    _build_metadata,
    _make_doc_id,
    atomize,
)
from pipeline.state import Activity


def _sample_activity() -> Activity:
    return {
        "wbs_activity_id": None,
        "l5_disc": "건축",
        "l6_main": "철근콘크리트공사",
        "l7_sub": None,
        "l7_5_activity": None,
        "sub_work_area": None,
        "trade": "건축",
        "company": "남웅건설",
        "unit": "m2",
        "today_qty": 0.0,
        "work_content": "기초 거푸집 설치",
        "conditions": [],
        "assigned_workers": 88.0,
        "worker_source": "mh_prorated",
        "plan_total_qty": None,
        "plan_mh": None,
        "wa": "CUB",
        "mapping_conf": 0.82,
        "mapping_source": "auto_bp_single",
        "requires_review": False,
    }


# ===== Step 2 — 6 unit (no I/O) =====


def test_make_doc_id_determinism():
    """spec §4.7 ✓ Verified."""
    id1 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    id2 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    assert id1 == id2 == "73ff80435e312c41"


def test_make_doc_id_changes():
    id1 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 거푸집 설치")
    id2 = _make_doc_id("2025-09-25", "남웅건설", "철근콘크리트공사", "기초 타설")
    assert id1 != id2


def test_make_doc_id_format():
    id_ = _make_doc_id("2025-09-25", "ZZZ", "L6", "WORK")
    assert len(id_) == 16
    assert all(c in "0123456789abcdef" for c in id_)


def test_build_metadata_scalar_only():
    meta = _build_metadata(_sample_activity(), "2025-09-25", "test-run")
    for k, v in meta.items():
        assert isinstance(v, (str, int, float, bool)), f"{k} = {type(v).__name__}"


def test_build_metadata_conditions_csv():
    a = _sample_activity()
    a["conditions"] = ["우천", "병행작업"]
    meta = _build_metadata(a, "2025-09-25", "test-run")
    assert meta["conditions"] == "우천,병행작업"


def test_build_metadata_none_to_empty_string():
    a = _sample_activity()
    a["wa"] = None
    meta = _build_metadata(a, "2025-09-25", "test-run")
    assert meta["wa"] == ""


# ===== Step 5 — 5 integration (실 Azure + Chroma + PG) =====


@pytest.fixture
def cfg() -> AtomizerConfig:
    keys = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_API_VERSION",
        "EMBEDDING_MODEL",
        "POSTGRES_URL",
        "CHROMA_HOST",
    ]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        pytest.skip(f"env 누락: {missing}")
    return AtomizerConfig(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        embedding_model=os.environ["EMBEDDING_MODEL"],
        postgres_url=os.environ["POSTGRES_URL"],
        chroma_host=os.environ["CHROMA_HOST"],
        chroma_port=int(os.environ.get("CHROMA_PORT", "8000")),
        chroma_ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )


@pytest.fixture
async def run_row(cfg):
    from pipeline.db import PGClient

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        run_id = uuid.uuid4()
        await pg.insert_pipeline_run(run_id, "M15X_PH3_IBL", "2025-09-25")
        yield run_id
        await pg.delete_pipeline_run(run_id)
    finally:
        await pg.close()


@pytest.mark.slow
async def test_atomize_empty():
    """valid=[] → return [], Azure/Chroma/PG 호출 없음."""
    cfg = AtomizerConfig(
        azure_endpoint="",
        azure_api_key="",
        azure_api_version="",
        embedding_model="",
        postgres_url="",
        chroma_host="",
        chroma_port=0,
    )
    parsed = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    result = await atomize([], parsed, uuid.uuid4(), cfg)
    assert result == []


@pytest.mark.slow
async def test_atomize_skip_unmapped(cfg):
    """l6_main=None Activity → skip."""
    parsed = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    mapped = [{**_sample_activity(), "l6_main": None}]
    result = await atomize(mapped, parsed, uuid.uuid4(), cfg)
    assert result == []


@pytest.mark.slow
async def test_atomize_namwong_47(cfg, run_row):
    """9/25 남웅 47 row (비계 제외) → Chroma 적재 + assigned_workers=88 일관.

    Spec §4.2 의 doc_id = sha256(date|company|l6_main|work_content)[:16] 는 같은
    (BP사, l6, work_content) 조합을 단일 doc 로 collapse. 9/25 남웅 47 row 의
    work_content 는 11 unique (예: '철근 배근' 12x, '기초 거푸집 설치' 7x …) →
    Chroma 적재 행은 11.
    """
    from pipeline.agents.mapper import _prorate_mh
    from pipeline.agents.parser import parse_daily_report
    from pipeline.chroma_client import ChromaClient
    from pipeline.db import PGClient

    xlsx_path = (
        "/Users/kyungseoplee/Project Agent/CPIA/docs/sample/"
        "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    )
    parsed = parse_daily_report(xlsx_path)

    namwong_raw = [a for a in parsed["activities"] if a["company"] == "남웅건설"]
    assert len(namwong_raw) == 48, f"남웅 행 수: {len(namwong_raw)} (예상 48)"
    namwong = [
        {
            **a,
            "wa": "CUB",
            "l6_main": "철근콘크리트공사",
            "mapping_conf": 0.82,
            "mapping_source": "auto_bp_single",
            "requires_review": False,
        }
        for a in namwong_raw
        if "비계" not in a["work_content"]
    ]
    assert len(namwong) == 47, f"비계 제외 후: {len(namwong)} (예상 47)"

    pg = PGClient(cfg.postgres_url)
    await pg.connect()
    try:
        namwong = await _prorate_mh(namwong, parsed, pg)
    finally:
        await pg.close()

    assert all(a["assigned_workers"] == 88.0 for a in namwong), (
        f"assigned_workers 값들: {set(a['assigned_workers'] for a in namwong)}"
    )

    ids = await atomize(namwong, parsed, run_row, cfg)
    # 47 input rows → 11 unique doc_id 로 collapse (work_content 가 반복됨).
    assert len(ids) == 11, f"unique doc_id 수: {len(ids)} (예상 11)"
    assert len(set(ids)) == len(ids), "atomize() 가 dedup 후 반환해야 함"

    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_daily_activities()
    rows = coll.get(ids=ids, include=["metadatas"])
    assert len(rows["ids"]) == 11
    assert all(m["assigned_workers"] == 88.0 for m in rows["metadatas"])


@pytest.mark.slow
async def test_atomize_upsert_idempotent(cfg, run_row):
    """같은 doc_id 2회 → row 수 같음 (upsert dedup)."""
    parsed = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    mapped = [_sample_activity()]
    ids1 = await atomize(mapped, parsed, run_row, cfg)
    ids2 = await atomize(mapped, parsed, run_row, cfg)
    assert ids1 == ids2


@pytest.mark.slow
async def test_atomize_missing_run_raises(cfg):
    """fixture 없이 호출 → RuntimeError (pipeline_runs 미존재)."""
    parsed = {
        "report_date": "2025-09-25",
        "project": "test",
        "bp_summaries": [],
        "job_allocations": [],
        "equipment_allocations": [],
        "activities": [],
    }
    mapped = [_sample_activity()]
    fake_id = uuid.uuid4()
    with pytest.raises(RuntimeError, match="pipeline_runs.*미존재"):
        await atomize(mapped, parsed, fake_id, cfg)
