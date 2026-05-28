# pipeline/tests/test_exporter_node.py
"""(Task 3) consolidated_xlsx_node — graph 노드 wrapper (D-1 / D-3 / D-7)."""

from __future__ import annotations

from datetime import date as _date
from unittest.mock import AsyncMock, patch

import pytest

from pipeline.agents.exporter import (
    NoDataError,
    SheetData,
    consolidated_xlsx_node,
)

pytestmark = pytest.mark.asyncio


def _base_state(run_id: str = "00000000-0000-0000-0000-000000000001") -> dict:
    return {
        "run_id": run_id,
        "site_id": "m15x-ph3-ibl",
        "date": "2025-09-25",
        "postgres_url": "postgresql://test",
        "project": "M15X Ph-3 IBL",
        "input_files": ["/tmp/fake.xlsx"],
    }


async def test_happy_path_upsert_and_meta() -> None:
    """fetch -> render -> upsert 4 단계 정상."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[{"bp_code": "X"}],
        occupation_manpower=[],
        equipment=[],
        quantity=[],
    )

    with (
        patch(
            "pipeline.agents.exporter.PGClient",
            return_value=fake_pg,
        ),
        patch(
            "pipeline.agents.exporter.fetch_sheet_data",
            new=AsyncMock(return_value=fake_sheet_data),
        ) as mock_fetch,
        patch(
            "pipeline.agents.exporter.fetch_site_by_id",
            new=AsyncMock(return_value={"name": "M15X 현장"}),
        ),
        patch(
            "pipeline.agents.exporter.render_xlsx",
            return_value=b"FAKE-RENDERED-BYTES",
        ) as mock_render,
        patch(
            "pipeline.agents.exporter.upsert_consolidated_report",
            new=AsyncMock(),
        ) as mock_upsert,
    ):
        out = await consolidated_xlsx_node(_base_state())

    mock_fetch.assert_awaited_once()
    fetch_args = mock_fetch.await_args
    assert fetch_args.args[1] == "m15x-ph3-ibl"
    assert fetch_args.args[2] == _date(2025, 9, 25)
    mock_render.assert_called_once_with(fake_sheet_data, _date(2025, 9, 25), project="M15X 현장")
    mock_upsert.assert_awaited_once()
    upsert_kwargs = mock_upsert.await_args.kwargs
    assert upsert_kwargs["xlsx_bytes"] == b"FAKE-RENDERED-BYTES"
    assert upsert_kwargs["site_id"] == "m15x-ph3-ibl"
    assert upsert_kwargs["report_date"] == _date(2025, 9, 25)
    fake_pg.close.assert_awaited_once()
    assert out["consolidated_xlsx_run_id"] == "00000000-0000-0000-0000-000000000001"
    assert out["consolidated_xlsx_generated_at"].endswith("Z")


async def test_no_data_error_skip_upsert() -> None:
    """fetch_sheet_data 가 NoDataError raise -- skip + return {}."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    with (
        patch(
            "pipeline.agents.exporter.PGClient",
            return_value=fake_pg,
        ),
        patch(
            "pipeline.agents.exporter.fetch_sheet_data",
            new=AsyncMock(side_effect=NoDataError("no data")),
        ),
        patch(
            "pipeline.agents.exporter.upsert_consolidated_report",
            new=AsyncMock(),
        ) as mock_upsert,
    ):
        out = await consolidated_xlsx_node(_base_state())

    assert out == {}
    mock_upsert.assert_not_awaited()
    fake_pg.close.assert_awaited_once()


async def test_render_exception_swallowed_close_pg() -> None:
    """render_xlsx 예외 swallow — return {} + log.exception + PG close 보장 (거동 B 대응)."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[],
        occupation_manpower=[],
        equipment=[],
        quantity=[],
    )

    with (
        patch(
            "pipeline.agents.exporter.PGClient",
            return_value=fake_pg,
        ),
        patch(
            "pipeline.agents.exporter.fetch_sheet_data",
            new=AsyncMock(return_value=fake_sheet_data),
        ),
        patch(
            "pipeline.agents.exporter.fetch_site_by_id",
            new=AsyncMock(return_value={"name": "X"}),
        ),
        patch(
            "pipeline.agents.exporter.render_xlsx",
            side_effect=ValueError("openpyxl 실패"),
        ),
        patch(
            "pipeline.agents.exporter.upsert_consolidated_report",
            new=AsyncMock(),
        ) as mock_upsert,
    ):
        out = await consolidated_xlsx_node(_base_state())

    assert out == {}  # swallow: no meta returned
    mock_upsert.assert_not_awaited()  # render failed, upsert not reached
    fake_pg.close.assert_awaited_once()  # finally still runs


async def test_project_fallback_state_project() -> None:
    """fetch_site_by_id 가 None 반환 시 state.project fallback."""
    fake_pg = AsyncMock()
    fake_pg.connect = AsyncMock()
    fake_pg.close = AsyncMock()

    fake_sheet_data = SheetData(
        output_manpower=[{}],
        occupation_manpower=[],
        equipment=[],
        quantity=[],
    )

    with (
        patch(
            "pipeline.agents.exporter.PGClient",
            return_value=fake_pg,
        ),
        patch(
            "pipeline.agents.exporter.fetch_sheet_data",
            new=AsyncMock(return_value=fake_sheet_data),
        ),
        patch(
            "pipeline.agents.exporter.fetch_site_by_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "pipeline.agents.exporter.render_xlsx",
            return_value=b"X",
        ) as mock_render,
        patch(
            "pipeline.agents.exporter.upsert_consolidated_report",
            new=AsyncMock(),
        ),
    ):
        await consolidated_xlsx_node(_base_state())

    assert mock_render.call_args.kwargs["project"] == "M15X Ph-3 IBL"
    fake_pg.close.assert_awaited_once()
