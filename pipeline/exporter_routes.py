"""FastAPI /export/run endpoint — Spec §7.3."""

from __future__ import annotations

import os
from datetime import date as _date

from fastapi import APIRouter, HTTPException, Response

from pipeline.agents.exporter import NoDataError, fetch_sheet_data, render_xlsx
from pipeline.db import PGClient, fetch_site_by_id

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/run")
async def export_consolidated(site_id: str, date: str) -> Response:
    try:
        report_date = _date.fromisoformat(date)
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")

    pg = PGClient(os.environ["POSTGRES_URL"])
    await pg.connect()
    try:
        site = await fetch_site_by_id(pg, site_id)
        if not site:
            raise HTTPException(404, f"site_id={site_id} 없음")
        try:
            data = await fetch_sheet_data(pg, site_id, report_date)
        except NoDataError as e:
            raise HTTPException(400, str(e))
    finally:
        await pg.close()

    xlsx_bytes = render_xlsx(data, report_date, project=site.get("name") or "CPIA")
    filename = f"통합작업일보_{date}.xlsx"
    # Content-Disposition 에 한글 파일명 포함 — HTTP header 는 기본 latin-1 이라
    # starlette Response(headers=...) 가 인코딩 실패. raw_headers 에 UTF-8 바이트로
    # 직접 주입한다 (RFC 6266 호환 클라이언트가 UTF-8 로 디코딩).
    resp = Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    cd_value = f'attachment; filename="{filename}"'.encode("utf-8")
    resp.raw_headers.append((b"content-disposition", cd_value))
    return resp
