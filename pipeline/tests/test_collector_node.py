"""collector_node — 파일명 검증 + 메타 분해 + collector_inbox UPDATE (D-12)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.agents.collector_node import collector_node


pytestmark = pytest.mark.asyncio


@pytest.fixture
def integrated_xlsx(tmp_path: Path) -> Path:
    """파일명 규약 통과 + 실 존재."""
    p = tmp_path / "통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
    p.write_bytes(b"dummy")
    return p


async def test_collector_node_extracts_meta(integrated_xlsx: Path) -> None:
    state = {
        "run_id": "00000000-0000-0000-0000-000000000001",
        "input_files": [str(integrated_xlsx)],
        # message_id 없음 → collector_inbox UPDATE skip
    }
    out = await collector_node(state)
    assert out["bp_name"] == "_integrated"
    assert out["report_date"] == "2025-09-25"
    assert out["project"] == "M15X Ph-3 IBL PJT 작업일보"


async def test_collector_node_updates_inbox_when_message_id(integrated_xlsx: Path) -> None:
    # PGClient 는 connect()/close() 패턴 (async with 미지원, pipeline/db.py:15+ 확인)
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()
    state = {
        "run_id": "00000000-0000-0000-0000-000000000002",
        "input_files": [str(integrated_xlsx)],
        "message_id": "<abc@example.com>#att.xlsx",
        "postgres_url": "postgresql://x",
    }
    with patch("pipeline.agents.collector_node.PGClient", return_value=fake_pg), \
         patch("pipeline.agents.collector_node.update_collector_inbox_status",
               new=AsyncMock()) as mock_update:
        await collector_node(state)
    mock_update.assert_awaited_once_with(
        fake_pg, "<abc@example.com>#att.xlsx",
        run_id=state["run_id"], parse_status="running",
    )
    fake_pg.close.assert_awaited_once()


async def test_collector_node_raises_on_missing_file(tmp_path: Path) -> None:
    state = {
        "run_id": "00000000-0000-0000-0000-000000000003",
        "input_files": [str(tmp_path / "nonexistent.xlsx")],
    }
    with pytest.raises(FileNotFoundError):
        await collector_node(state)


async def test_collector_node_raises_on_bad_filename(tmp_path: Path) -> None:
    bad = tmp_path / "random.xlsx"; bad.write_bytes(b"x")
    state = {"run_id": "x", "input_files": [str(bad)]}
    with pytest.raises(ValueError):
        await collector_node(state)
