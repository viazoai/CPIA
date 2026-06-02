"""C5-6: /run _bg 실패 시 mapper_activities 부분행 DELETE + pipeline_runs 'failed' 마킹.

테스트 전략: mock-based (Fallback 경로).
  - live PG 없이 결정론적 검증 가능.
  - sys.modules["asyncpg"] 를 fake_asyncpg 로 교체해서 _bg 안의
    `import asyncpg as _asyncpg` 가 recorder 를 가져오도록 한다.
  - (a) DELETE FROM mapper_activities WHERE run_id=$1 이 run_id 인자와 함께 호출됐는지,
    (b) set_run_status(..., "failed") 호출 이전에 DELETE 가 실행됐는지
    를 call_order 순서 기록으로 검증한다.
  - 기존 test_api_hil1_resume.py 와 동일한 패턴 (lifespan + ASGITransport + monkeypatch).

선택 이유: /run 엔드포인트는 input_dir 존재 확인을 하므로 live filesystem 셋업이 필요하다.
  테스트 범위를 _bg except handler 배선으로 좁혀 live PG 없이 결정론적으로 검증하는
  mock-based 접근이 가장 신뢰도 높다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import pipeline.api as api_module
from pipeline.api import app


# ---------------------------------------------------------------------------
# 공용 fixture
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """테스트 격리 환경 변수 + 입력 디렉토리 셋업."""
    monkeypatch.setenv("CPIA_CHECKPOINTER", "memory")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://test:test@localhost:5432/test")

    # /run 엔드포인트가 input_dir 존재 + .xlsx 파일을 확인한다 — dummy 파일 생성.
    date_dir = tmp_path / "input" / "20250925"
    date_dir.mkdir(parents=True)
    (date_dir / "report.xlsx").write_bytes(b"dummy")

    # _DATA_DIR 을 tmp_path 로 교체.
    monkeypatch.setattr(api_module, "_DATA_DIR", tmp_path)


@pytest.fixture()
def mock_pg() -> MagicMock:
    """PGClient 완전 mock."""
    pg = MagicMock()
    pg.connect = AsyncMock()
    pg.close = AsyncMock()
    pg.fetch_one = AsyncMock(return_value={"ok": 1})
    pg.insert_pipeline_run = AsyncMock()
    return pg


# ---------------------------------------------------------------------------
# 핵심 테스트: _bg 예외 시 DELETE 가 set_run_status 보다 먼저 실행됨
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_bg_cleanup_deletes_mapper_activities_before_failed(
    mock_pg: MagicMock,
) -> None:
    """graph.ainvoke 가 실패하면 _bg 는:
    1. DELETE FROM mapper_activities WHERE run_id=$1 을 run_id 인자로 실행하고,
    2. 그 이후에 set_run_status(..., 'failed') 를 호출한다.

    call_order 순서 기록으로 (1) before (2) 를 검증.
    """
    failing_graph = MagicMock()
    failing_graph.ainvoke = AsyncMock(side_effect=RuntimeError("mapper mid-run failure"))

    call_order: list[str] = []

    # asyncpg connection recorder — execute 호출을 call_order 에 기록.
    mock_conn = MagicMock()

    async def _fake_execute(sql: str, *args: Any) -> None:
        if "mapper_activities" in sql:
            call_order.append(f"DELETE:{args[0] if args else 'NO_ARG'}")

    mock_conn.execute = _fake_execute
    mock_conn.close = AsyncMock()

    async def _fake_connect(url: str) -> Any:
        return mock_conn

    # set_run_status recorder.
    async def _fake_set_run_status(url: str, run_id: Any, status: str) -> None:
        call_order.append(f"STATUS:{status}")

    # insert_pipeline_run 에서 run_id 를 캡처 (검증용).
    captured_run_id: list[Any] = []

    async def _capture_insert(run_id: Any, **kw: Any) -> None:
        captured_run_id.append(run_id)

    mock_pg.insert_pipeline_run = _capture_insert

    # fake_asyncpg: _bg 내부의 `import asyncpg as _asyncpg` 가 이 객체를 가져온다.
    fake_asyncpg = MagicMock()
    fake_asyncpg.connect = AsyncMock(side_effect=_fake_connect)

    original_asyncpg = sys.modules.get("asyncpg")
    sys.modules["asyncpg"] = fake_asyncpg  # type: ignore[assignment]
    try:
        with (
            patch.object(api_module, "PGClient", return_value=mock_pg),
            patch.object(api_module, "build_graph", return_value=failing_graph),
            patch.object(api_module, "_build_prod_graph_config", return_value=MagicMock()),
            patch.object(api_module, "set_run_status", side_effect=_fake_set_run_status),
        ):
            async with api_module.lifespan(app):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    res = await client.post(
                        "/run",
                        json={"site_id": "m15x-ph3-ibl", "report_date": "20250925"},
                    )
                    assert res.status_code == 200, res.text
                    # _bg 백그라운드 task 완료 대기: ainvoke → except → DELETE → set_run_status.
                    await asyncio.sleep(0.15)
    finally:
        if original_asyncpg is None:
            sys.modules.pop("asyncpg", None)
        else:
            sys.modules["asyncpg"] = original_asyncpg

    # (a) DELETE 가 호출됐는지
    delete_calls = [e for e in call_order if e.startswith("DELETE:")]
    assert delete_calls, f"DELETE 호출 없음. call_order={call_order}"

    # (b) DELETE 에 전달된 run_id 가 pipeline_runs 행 run_id 와 일치하는지
    assert captured_run_id, "insert_pipeline_run 이 호출되지 않음"
    expected_run_id = captured_run_id[0]  # uuid.UUID
    assert any(str(expected_run_id) in e for e in delete_calls), (
        f"DELETE 인자 불일치. expected={expected_run_id}, calls={delete_calls}"
    )

    # (c) DELETE 가 set_run_status('failed') 보다 먼저 발생했는지
    assert "STATUS:failed" in call_order, f"set_run_status('failed') 미호출. call_order={call_order}"
    first_delete_idx = next(i for i, e in enumerate(call_order) if e.startswith("DELETE:"))
    status_failed_idx = call_order.index("STATUS:failed")
    assert first_delete_idx < status_failed_idx, (
        f"DELETE({first_delete_idx}) 가 STATUS:failed({status_failed_idx}) 보다 늦음. call_order={call_order}"
    )
