"""Master List xlsx → PG activity_master + Chroma wbs_master 동시 적재.

Spec: docs/schema/mapping-layer.md §5

사용:
    uv run scripts/load_master_list.py --filter-companies 남웅건설 세보엠이씨 창원기전
    uv run scripts/load_master_list.py            # 전체 적재
    uv run scripts/load_master_list.py --dry-run  # 적재 없이 카운트만
"""

from __future__ import annotations

import argparse
import asyncio
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

import asyncpg
import openpyxl
from dotenv import load_dotenv
from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient

CPIA_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(CPIA_ROOT / ".env")


# Master List 컬럼 인덱스 (sample 실 데이터 검증 — Step 0)
C_AID = 1  # ActivityID (Rev.0)
C_WA = 4  # Work Area (CUB/FAB)
C_WA_NAME = 5  # Work Area 명칭
C_L5 = 14  # L5 Discipline ('건축'/'설비'/'전기'/...)
C_L6 = 16  # L6 Work PKG-1 ('철근콘크리트공사' 등)
C_L7 = 18  # L7 Work PKG-2
C_L75 = 20  # L7.5 Activity
C_COMPANY = 24  # BP사
C_UNIT = 25  # 단위 (M2/Ton/M3/...) — _normalize_unit 으로 소문자 통일
C_PLAN_QTY = 30  # 총수량 Rev.2
C_PLAN_MH = 31  # MH Rev.2
C_PLAN_START = 37  # Planned Start Rev.2
C_PLAN_FINISH = 38  # Planned Finish Rev.2
C_ACTUAL_START = 41  # Actual Start Date
C_ACTUAL_FINISH = 42  # Actual Finish Date


def _normalize_unit(u: Any) -> str | None:
    """단위 소문자 통일 (EA / ea / M2 / m2 혼재 방지). Parser._normalize_unit 과 같은 정책."""
    if u is None:
        return None
    s = str(u).strip().lower()
    return s or None


def _to_date(v: Any) -> Any:
    """openpyxl 의 datetime → date 변환. 빈 셀이 time(0,0) 으로 오는 패턴 None 처리."""
    from datetime import date as _date
    from datetime import datetime as _datetime

    if isinstance(v, _datetime):
        return v.date()
    if isinstance(v, _date):
        return v
    return None


def parse_master_groups(
    xlsx_path: Path,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Master List xlsx → (WA, L6) 그룹 dict. 각 그룹 안에 row 들 보존."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Master List"]
    rows = list(ws.iter_rows(values_only=True))[4:]  # R5~ (헤더 4행)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if not r[C_AID]:
            continue
        wa = r[C_WA]
        l6 = r[C_L6]
        if not wa or not l6:
            continue
        groups[(wa, l6)].append(
            {
                "wbs_activity_id": r[C_AID],
                "wa": wa,
                "wa_name": r[C_WA_NAME],
                "l5": r[C_L5],
                "l6": l6,
                "l7": r[C_L7],
                "l75": r[C_L75],
                "company": r[C_COMPANY],
                "unit": _normalize_unit(r[C_UNIT]),
                "plan_total_qty": r[C_PLAN_QTY],
                "plan_mh_rev2": r[C_PLAN_MH],
                "plan_start": _to_date(r[C_PLAN_START]),
                "plan_finish": _to_date(r[C_PLAN_FINISH]),
                "actual_start": _to_date(r[C_ACTUAL_START]),
                "actual_finish": _to_date(r[C_ACTUAL_FINISH]),
            }
        )
    wb.close()
    return dict(groups)


def make_doc_text(wa: str, l6: str, rows: list[dict[str, Any]]) -> str:
    """Chroma wbs_master doc text — mapping-layer.md §5.2 형식."""
    wa_names = sorted({r["wa_name"] for r in rows if r["wa_name"]})
    l5s = sorted({r["l5"] for r in rows if r["l5"]})
    l7s = sorted({r["l7"] for r in rows if r["l7"]})
    l75s = sorted({r["l75"] for r in rows if r["l75"]})
    cos = sorted({r["company"] for r in rows if r["company"]})
    units = sorted({r["unit"] for r in rows if r["unit"]})

    return (
        f"Work Area: {wa} ({', '.join(wa_names)})\n"
        f"Discipline (L5): {l5s[0] if l5s else ''}\n"
        f"Work PKG-1 (L6): {l6}\n"
        f"Work PKG-2 (L7): {', '.join(l7s)}\n"
        f"Units: {', '.join(units)}\n"
        f"Activities (L7.5 sample): {', '.join(l75s[:8])}\n"
        f"Companies: {', '.join(cos[:8])}"
    )


async def upsert_pg(
    rows: list[dict[str, Any]],
    dsn: str,
    source_file: str,
) -> int:
    """PG activity_master row 별 UPSERT."""
    conn = await asyncpg.connect(dsn)
    try:
        inserted = 0
        for r in rows:
            await conn.execute(
                """
                INSERT INTO activity_master (
                    wbs_activity_id, wa, l5_disc, l6_main, l7_sub, l7_5_activity,
                    company, unit, plan_total_qty, plan_mh_rev2,
                    plan_start, plan_finish, actual_start, actual_finish, source_file
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (wbs_activity_id) DO UPDATE SET
                    unit = EXCLUDED.unit,
                    plan_total_qty = EXCLUDED.plan_total_qty,
                    plan_mh_rev2 = EXCLUDED.plan_mh_rev2,
                    plan_start = EXCLUDED.plan_start,
                    plan_finish = EXCLUDED.plan_finish,
                    actual_start = EXCLUDED.actual_start,
                    actual_finish = EXCLUDED.actual_finish,
                    loaded_at = now()
                """,
                r["wbs_activity_id"],
                r["wa"],
                r["l5"],
                r["l6"],
                r["l7"],
                r["l75"],
                r["company"],
                r["unit"],
                r["plan_total_qty"],
                r["plan_mh_rev2"],
                r["plan_start"],
                r["plan_finish"],
                r["actual_start"],
                r["actual_finish"],
                source_file,
            )
            inserted += 1
        return inserted
    finally:
        await conn.close()


def upsert_chroma(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    azure: AzureOpenAI,
    embed_model: str,
) -> int:
    """Chroma wbs_master 에 (WA, L6) 그룹 단위로 임베딩 적재."""
    chroma = ChromaClient(
        host=os.environ["CHROMA_HOST"],
        port=int(os.environ.get("CHROMA_PORT", "8000")),
        ssl=os.environ.get("CHROMA_SSL", "false").lower() == "true",
    )
    coll = chroma.get_or_create_wbs_master()

    ids: list[str] = []
    texts: list[str] = []
    metas: list[dict[str, Any]] = []
    for (wa, l6), rows in sorted(groups.items()):
        ids.append(f"{wa}|{l6}")
        texts.append(make_doc_text(wa, l6, rows))
        companies = sorted({r["company"] for r in rows if r["company"]})
        units = sorted({r["unit"] for r in rows if r["unit"]})
        l5s = sorted({r["l5"] for r in rows if r["l5"]})
        metas.append(
            {
                "wa": wa,
                "l6_main": l6,
                "l5_disc": l5s[0] if l5s else "",
                "companies": ",".join(companies),
                "units": ",".join(units),
            }
        )

    # 임베딩 — 16개씩 batch
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), 16):
        chunk = texts[i : i + 16]
        resp = azure.embeddings.create(model=embed_model, input=chunk)
        embeddings.extend([d.embedding for d in resp.data])

    coll.upsert(ids=ids, embeddings=embeddings, metadatas=metas, documents=texts)
    return len(ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--wbs",
        type=Path,
        default=CPIA_ROOT / "docs/sample/WBS공정표_M15X IBL PH-3_CPRS_2025.09.25.xlsx",
    )
    ap.add_argument(
        "--filter-companies",
        nargs="*",
        default=None,
        help="적재할 BP사 명단. 미지정 시 전체.",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print(f"[load] xlsx: {args.wbs}")
    groups = parse_master_groups(args.wbs)
    print(f"[load] 전체 (WA, L6) 그룹: {len(groups)}")

    if args.filter_companies:
        filter_set = set(args.filter_companies)
        groups = {
            k: [r for r in v if r["company"] in filter_set] for k, v in groups.items()
        }
        groups = {k: v for k, v in groups.items() if v}
        print(f"[load] filter 적용 후 그룹: {len(groups)}")

    all_rows = [r for rows in groups.values() for r in rows]
    print(f"[load] 적재 row: {len(all_rows)}")

    if args.dry_run:
        print("[load] dry-run 모드, 적재 생략")
        return

    # PG 적재
    dsn = os.environ["POSTGRES_URL"]
    n_pg = asyncio.run(upsert_pg(all_rows, dsn, str(args.wbs.name)))
    print(f"[load] PG activity_master upsert: {n_pg} rows")

    # Chroma 적재 (Azure OpenAI 임베딩)
    azure = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    )
    n_chr = upsert_chroma(groups, azure, os.environ["EMBEDDING_MODEL"])
    print(f"[load] Chroma wbs_master upsert: {n_chr} groups")


if __name__ == "__main__":
    main()
