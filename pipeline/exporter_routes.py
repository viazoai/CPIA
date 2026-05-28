"""FastAPI /export/run endpoint — (D-5 E-2) hybrid + #N21 부분 해소."""

from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter, HTTPException, Request, Response

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx
from pipeline.db import fetch_consolidated_report, fetch_site_by_id

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/run")
async def export_consolidated(
    request: Request,
    site_id: str,
    date: str,
) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = request.app.state.pg

    cached = await fetch_consolidated_report(
        pg,
        site_id=site_id,
        report_date=report_date,
    )
    if cached is not None:
        return _build_xlsx_response(cached, date)

    site = await fetch_site_by_id(pg, site_id)
    if not site:
        raise HTTPException(404, f"site_id={site_id} 없음")
    try:
        data = await fetch_sheet_data(pg, site_id, report_date)
    except NoDataError as e:
        raise HTTPException(400, str(e))
    xlsx_bytes = render_xlsx(
        data,
        report_date,
        project=site.get("name") or "CPIA",
    )
    return _build_xlsx_response(xlsx_bytes, date)


def _build_xlsx_response(xlsx_bytes: bytes, date: str) -> Response:
    """Content-Disposition UTF-8 raw_headers 패치 (한글 파일명, 선행 a7e2465)."""
    filename = f"통합작업일보_{date}.xlsx"
    resp = Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp.raw_headers.append(
        (
            b"content-disposition",
            f'attachment; filename="{filename}"'.encode("utf-8"),
        )
    )
    return resp
