"""Step B: L7.5 임베딩 재매핑 (9-25 prototype).

mapper_activities 의 9-25 건축/토목 매칭 row (357개) 각각에 대해:
  - parser_activities.work_content (텍스트) 가져옴
  - activity_master 의 (site, company, l6_main) 안의 L7.5 후보 N개 가져옴
  - N=1 즉시 매핑 / N>=2 cosine 임베딩 매칭 (Azure OpenAI text-embedding-3-small 1536d)
  - 결과 prototype_l7_5_resolved 적재 (mapper_id PK)
"""

from __future__ import annotations

import asyncio
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


async def embed_batch(
    client: AsyncAzureOpenAI, texts: list[str]
) -> dict[str, list[float]]:
    if not texts:
        return {}
    # batch size 100 (Azure 안전)
    out: dict[str, list[float]] = {}
    for i in range(0, len(texts), 100):
        chunk = texts[i : i + 100]
        resp = await client.embeddings.create(input=chunk, model=EMBED_MODEL)
        for t, d in zip(chunk, resp.data):
            out[t] = d.embedding
    return out


async def main() -> None:
    from datetime import date as _date  # ruff F401 회피

    proto = _date.fromisoformat(PROTO_DATE_STR)

    pg = await asyncpg.connect(DSN)
    client = AsyncAzureOpenAI(
        api_key=AZURE_KEY,
        azure_endpoint=AZURE_ENDPOINT,
        api_version=AZURE_VERSION,
    )

    try:
        await pg.execute(CREATE_SQL)
        await pg.execute("TRUNCATE prototype_l7_5_resolved")

        rows = await pg.fetch(
            """
            SELECT ma.id AS mapper_id, ma.run_id, ma.report_date, pr.site_id,
                   ma.company, ma.l6_main, ma.idx, pa.work_content
            FROM mapper_activities ma
            JOIN pipeline_runs pr USING (run_id)
            LEFT JOIN parser_activities pa USING (run_id, idx)
            WHERE ma.report_date = $1
              AND EXISTS (
                  SELECT 1 FROM activity_master am
                  WHERE am.site_id = pr.site_id
                    AND am.company = ma.company
                    AND am.l6_main = ma.l6_main
                    AND am.l5_disc IN ('건축','토목')
              )
            """,
            proto,
        )
        print(f"mapper rows (9-25, civ match): {len(rows)}")

        # (site, company, l6) -> L7.5 후보 collect
        cand_map: dict[tuple, list[dict]] = defaultdict(list)
        keys = {(r["site_id"], r["company"], r["l6_main"]) for r in rows}
        for site, comp, l6 in keys:
            cs = await pg.fetch(
                """
                SELECT l7_5_activity, unit, plan_total_qty, plan_mh_rev2
                FROM activity_master
                WHERE site_id = $1 AND company = $2 AND l6_main = $3
                  AND l7_5_activity IS NOT NULL
                """,
                site,
                comp,
                l6,
            )
            cand_map[(site, comp, l6)] = [dict(c) for c in cs]

        # 임베딩 대상 텍스트 collect
        all_wc = sorted({r["work_content"] for r in rows if r["work_content"]})
        all_l75 = sorted({c["l7_5_activity"] for cs in cand_map.values() for c in cs})
        print(f"embeddings: work_content={len(all_wc)}, l7_5={len(all_l75)}")

        wc_emb = await embed_batch(client, all_wc)
        l75_emb = await embed_batch(client, all_l75)

        # row 매칭
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

        # stats
        with_match = sum(1 for _, m, _, _ in resolved if m)
        embed_used = sum(1 for _, _, _, n in resolved if n >= 2)
        scores = [s for _, m, s, _ in resolved if m and s > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        print(
            f"\nResolved: total={len(resolved)} matched={with_match} "
            f"({100 * with_match / len(resolved):.1f}%) "
            f"single-cand={len(resolved) - embed_used} "
            f"embed-cand={embed_used}"
        )
        print(f"avg cosine score (matched, embed-cand): {avg_score:.3f}")
    finally:
        await pg.close()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
