"""L7.5 임베딩 재매핑 (Phase 1: 530일 확장).

mapper_activities 의 건축/토목 매칭 row 각각:
  - parser_activities.work_content 가져옴
  - activity_master 의 (site, company, l6_main) 안 L7.5 후보 N개 (master 캐시)
  - N=1 즉시 매핑 / N>=2 cosine 매칭 (Azure OpenAI text-embedding-3-small 1536d)
  - prototype_embedding_cache 활용 (재실행 시 Azure 호출 skip)
  - 결과 prototype_l7_5_resolved 적재

플랜 기간 필터: ma.report_date BETWEEN m.ps AND m.pf
(activity_master 의 같은 (site, company, l6) 그룹의 plan_start/plan_finish 합집합)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import math
import os
from collections import defaultdict
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from openai import AsyncAzureOpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

DSN = os.environ.get(
    "POSTGRES_URL",
    "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia",
)
AZURE_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
AZURE_KEY = os.environ["AZURE_OPENAI_API_KEY"]
AZURE_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
EMBED_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small-ai-board-test")
EMBED_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))

PROTO_DATE_STR = "2025-09-25"

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS prototype_l7_5_resolved (
  mapper_id bigint PRIMARY KEY,
  run_id uuid NOT NULL,
  report_date date NOT NULL,
  site_id text NOT NULL,
  company text NOT NULL,
  l6_main text NOT NULL,
  parser_work_content text,
  matched_l7_5_activity text,
  matched_unit text,
  matched_plan_total_qty numeric,
  matched_plan_mh numeric,
  match_score float,
  candidate_n int,
  resolved_at timestamptz DEFAULT now()
);
"""


def cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return s / (na * nb) if na * nb else 0.0


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


async def embed_with_cache(
    client: AsyncAzureOpenAI,
    pg: asyncpg.Connection,
    texts: list[str],
) -> dict[str, list[float]]:
    """texts 의 임베딩 dict. cache hit 면 PG 에서 / miss 면 Azure 호출 후 PG 적재."""
    if not texts:
        return {}
    out: dict[str, list[float]] = {}
    to_call: list[tuple[str, str]] = []  # (text, hash)
    for t in texts:
        if t in out:
            continue
        h = text_hash(t)
        row = await pg.fetchrow(
            "SELECT embedding FROM prototype_embedding_cache WHERE text_hash = $1", h
        )
        if row:
            out[t] = list(row["embedding"])
        else:
            to_call.append((t, h))
    if to_call:
        for i in range(0, len(to_call), 100):
            chunk = to_call[i : i + 100]
            resp = await client.embeddings.create(
                input=[t for t, _ in chunk], model=EMBED_MODEL
            )
            for (t, h), d in zip(chunk, resp.data):
                out[t] = list(d.embedding)
                await pg.execute(
                    "INSERT INTO prototype_embedding_cache "
                    "(text_hash, source_text, embedding) "
                    "VALUES ($1, $2, $3) ON CONFLICT (text_hash) DO NOTHING",
                    h,
                    t,
                    out[t],
                )
    return out


async def load_candidates(
    pg: asyncpg.Connection,
) -> dict[tuple[str, str, str], list[dict]]:
    """activity_master 의 (site, company, l6_main) -> L7.5 후보 dict.
    한 번만 호출 — master 는 일자 무관."""
    rows = await pg.fetch(
        """
        SELECT site_id, company, l6_main,
               l7_5_activity, unit, plan_total_qty, plan_mh_rev2
        FROM activity_master
        WHERE l7_5_activity IS NOT NULL
          AND l5_disc IN ('건축','토목')
        """
    )
    out: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        out[(r["site_id"], r["company"], r["l6_main"])].append(dict(r))
    return out


async def fetch_rows_for_date(pg: asyncpg.Connection, the_date) -> list:
    """단일 일자의 mapper row + plan 안 필터.
    LATERAL JOIN 으로 (site, company, l6) 그룹의 plan 기간 합집합 계산."""
    return await pg.fetch(
        """
        SELECT ma.id AS mapper_id, ma.run_id, ma.report_date, pr.site_id,
               ma.company, ma.l6_main, ma.idx, pa.work_content
        FROM mapper_activities ma
        JOIN pipeline_runs pr USING (run_id)
        LEFT JOIN parser_activities pa USING (run_id, idx)
        LEFT JOIN LATERAL (
            SELECT MIN(plan_start) AS ps, MAX(plan_finish) AS pf
            FROM activity_master am
            WHERE am.site_id = pr.site_id
              AND am.company = ma.company
              AND am.l6_main = ma.l6_main
              AND am.l5_disc IN ('건축','토목')
        ) m ON TRUE
        WHERE ma.report_date = $1
          AND m.ps IS NOT NULL
          AND ma.report_date BETWEEN m.ps AND m.pf
        """,
        the_date,
    )


async def process_one_date(
    pg: asyncpg.Connection,
    client: AsyncAzureOpenAI,
    the_date,
    cand_map: dict[tuple[str, str, str], list[dict]],
) -> dict:
    rows = await fetch_rows_for_date(pg, the_date)
    if not rows:
        return {"date": str(the_date), "rows": 0, "matched": 0, "embed_calls": 0}

    # 임베딩 대상
    wc_texts = sorted({r["work_content"] for r in rows if r["work_content"]})
    l75_texts = sorted(
        {
            c["l7_5_activity"]
            for r in rows
            for c in cand_map.get((r["site_id"], r["company"], r["l6_main"]), [])
        }
    )

    # cache 활용 임베딩
    wc_emb = await embed_with_cache(client, pg, wc_texts)
    l75_emb = await embed_with_cache(client, pg, l75_texts)

    # 매칭
    resolved = []
    for r in rows:
        cands = cand_map.get((r["site_id"], r["company"], r["l6_main"]), [])
        if not cands:
            resolved.append((r, None, 0.0, 0))
            continue
        if len(cands) == 1:
            resolved.append((r, cands[0], 1.0, 1))
            continue
        wc = r["work_content"] or ""
        if not wc or wc not in wc_emb:
            resolved.append((r, cands[0], 0.0, len(cands)))
            continue
        wv = wc_emb[wc]
        scored = [
            (c, cosine(wv, l75_emb.get(c["l7_5_activity"], [0.0] * EMBED_DIM)))
            for c in cands
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        best, score = scored[0]
        resolved.append((r, best, score, len(cands)))

    # INSERT
    async with pg.transaction():
        for r, m, score, n in resolved:
            await pg.execute(
                """
                INSERT INTO prototype_l7_5_resolved (
                    mapper_id, run_id, report_date, site_id, company, l6_main,
                    parser_work_content, matched_l7_5_activity, matched_unit,
                    matched_plan_total_qty, matched_plan_mh, match_score, candidate_n
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT (mapper_id) DO UPDATE SET
                    matched_l7_5_activity = EXCLUDED.matched_l7_5_activity,
                    matched_unit = EXCLUDED.matched_unit,
                    matched_plan_total_qty = EXCLUDED.matched_plan_total_qty,
                    matched_plan_mh = EXCLUDED.matched_plan_mh,
                    match_score = EXCLUDED.match_score,
                    candidate_n = EXCLUDED.candidate_n,
                    resolved_at = now()
                """,
                r["mapper_id"],
                r["run_id"],
                r["report_date"],
                r["site_id"],
                r["company"],
                r["l6_main"],
                r["work_content"],
                m["l7_5_activity"] if m else None,
                m["unit"] if m else None,
                m["plan_total_qty"] if m else None,
                m["plan_mh_rev2"] if m else None,
                score,
                n,
            )

    return {
        "date": str(the_date),
        "rows": len(rows),
        "matched": sum(1 for _, m, _, _ in resolved if m),
        "embed_calls_wc": len(wc_texts),
        "embed_calls_l75": len(l75_texts),
    }


async def main() -> None:
    from datetime import date as _date

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date", default=None, help="단일 YYYY-MM-DD (기본 2025-09-25)"
    )
    parser.add_argument("--all-dates", action="store_true", help="530일 전체")
    args = parser.parse_args()

    pg = await asyncpg.connect(DSN)
    client = AsyncAzureOpenAI(
        api_key=AZURE_KEY,
        azure_endpoint=AZURE_ENDPOINT,
        api_version=AZURE_VERSION,
    )

    try:
        await pg.execute(CREATE_SQL)

        # 후보 dict 1회 load (master 는 일자 무관)
        cand_map = await load_candidates(pg)
        print(f"master 후보 그룹: {len(cand_map)} (site,company,l6)")

        # 처리 일자 목록
        if args.all_dates:
            date_rows = await pg.fetch(
                "SELECT DISTINCT report_date FROM mapper_activities ORDER BY 1"
            )
            dates = [r["report_date"] for r in date_rows]
            print(f"--all-dates: {len(dates)} 일자")
        else:
            d = _date.fromisoformat(args.date or PROTO_DATE_STR)
            dates = [d]
            print(f"단일 일자: {d}")
            # 단일 모드는 prior row 삭제 (재실행 안전)
            await pg.execute(
                "DELETE FROM prototype_l7_5_resolved WHERE report_date = $1", d
            )

        total_rows = 0
        total_matched = 0
        skip_dates = 0
        for d in dates:
            stat = await process_one_date(pg, client, d, cand_map)
            total_rows += stat["rows"]
            total_matched += stat["matched"]
            if stat["rows"] == 0:
                skip_dates += 1
            if args.all_dates and (
                d == dates[0]
                or d == dates[-1]
                or stat["rows"] > 0
                and (dates.index(d) % 50 == 0)
            ):
                print(f"  {stat}")
            elif not args.all_dates:
                print(f"  {stat}")

        # 요약
        cache_size = await pg.fetchval("SELECT COUNT(*) FROM prototype_embedding_cache")
        skip_pct = skip_dates / len(dates) * 100 if dates else 0
        print("\n=== 요약 ===")
        print(
            f"처리 일자: {len(dates)}, skip (plan 밖) 일자: {skip_dates} ({skip_pct:.1f}%)"
        )
        print(f"row total: {total_rows}, matched: {total_matched}")
        print(f"embedding_cache 누적: {cache_size}")
    finally:
        await pg.close()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
