"""Mapper agent — 작업일보 → WBS 매핑.

Spec: docs/schema/mapping-layer.md §3 (6단계 흐름) + §4 (WA 결정 4단계).

Task 6 (이 파일) — helper 함수 (build_embedding_input / build_llm_input /
build_bp_context / resolve_wa).
Task 7 — map_activity 통합 함수.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, BPSummary, ParsedDailyReport


# 시트2 직종 noise 제거 — mapping-layer.md §2.1 (3)
_TRADE_KEYWORDS = (
    "형틀",
    "철근",
    "콘크리트",
    "타설",
    "조적",
    "방수",
    "도장",
    "비계",
    "용접",
    "배관",
    "전기공",
    "덕트",
    "단열",
    "내장",
    "타일",
    "미장",
    "양생",
    "철골",
    "보온",
    "케이블",
)
_MGR_KEYWORDS = (
    "소장",
    "관리자",
    "감독",
    "감리",
    "안전",
    "Shop",
    "BIM",
    "공무",
    "설계",
    "품질",
    "운영",
    "창고",
)
_NOISE_KEYWORDS = ("기능공 투입 Total", "기능공 투입 total")


def _is_trade_job(job: str) -> bool:
    """시트2 직종 noise 제거."""
    if any(n in job for n in _NOISE_KEYWORDS):
        return False
    if any(m in job for m in _MGR_KEYWORDS):
        return False
    return any(k in job for k in _TRADE_KEYWORDS)


@dataclass(frozen=True)
class WAResolution:
    """WA 결정 결과."""

    value: str | None
    source: Literal[
        "auto_bp_single",
        "auto_l6_single",
        "auto_sheet1_text",
        "auto_chroma_top1",  # Task 4 — BP master 미등록 BP사 (cand_pool 빈 시)
        "hil_required",
    ]


def build_embedding_input(activity: Activity) -> str:
    """임베딩 input — 작업line 자체만 (mapping-layer.md §3.1).

    숫자·BP 컨텍스트 제외. v2 의 숫자 오염 (배관공 165168 등) 방지.
    """
    return (
        f"회사: {activity['company']}\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}\n"
        f"공종: {activity['trade']}"
    )


def build_bp_context(
    company: str,
    parsed_report: ParsedDailyReport | None,
) -> str:
    """LLM input 용 BP사 단위 풍부 컨텍스트 (시트1+2+3 join)."""
    if not parsed_report:
        return "  · (parsed_report 미제공 — BP 컨텍스트 없이 진행)"

    summaries: list[BPSummary] = [s for s in parsed_report["bp_summaries"] if s["company"] == company]
    work_texts = [s["work_text_today"] for s in summaries if s["work_text_today"]]
    today_incr = sum(s["today_incr_total"] for s in summaries)
    today_cum = sum(s["today_cum_total"] for s in summaries)
    work_text_str = " / ".join(t for t in work_texts[:2] if t)[:200] if work_texts else "미기재"

    sheet1_block = (
        f"  · [시트1] 주요작업 텍스트 (BP사 기재): {work_text_str}\n"
        f"  · [시트1] 금일 신규 투입 인원 (Incr.): {today_incr:,}명\n"
        f"  · [시트1] 금일 누적 인원 (Cum.): {today_cum:,}명-일"
    )

    # 시트2 — 기능공만, noise 제거
    jobs: dict[str, int] = {}
    for j in parsed_report["job_allocations"]:
        if j["company"] != company:
            continue
        if not _is_trade_job(j["job_type"]):
            continue
        jobs[j["job_type"]] = jobs.get(j["job_type"], 0) + j["workers_cum_t"]
    if jobs:
        top_jobs = sorted(jobs.items(), key=lambda x: -x[1])[:8]
        job_lines = "\n".join(f"      - {j}: {c:,}명-일" for j, c in top_jobs)
        sheet2_block = "  · [시트2] 기능공 직종 (금일누계 Cum.T):\n" + job_lines
    else:
        sheet2_block = "  · [시트2] 기능공 직종: 미신고"

    # 시트3 — 장비
    eqs = [e for e in parsed_report["equipment_allocations"] if e["company"] == company]
    if eqs:
        top_eq = sorted(eqs, key=lambda e: -e["count_cum_t"])[:5]
        eq_lines = "\n".join(
            f"      - {e['equipment_big']}/{e['equipment_mid']} "
            f"({e['equipment_spec'] or '규격 미상'}): {e['count_cum_t']:,}회-일"
            for e in top_eq
        )
        sheet3_block = "  · [시트3] 투입 장비 (금일투입누계 Cum.T):\n" + eq_lines
    else:
        sheet3_block = "  · [시트3] 투입 장비: 미신고"

    return f"{sheet1_block}\n{sheet2_block}\n{sheet3_block}"


def build_llm_input(
    activity: Activity,
    parsed_report: ParsedDailyReport | None,
) -> str:
    """LLM input — 작업line + BP사 단위 풍부 컨텍스트 (mapping-layer.md §3.1)."""
    bp_ctx = build_bp_context(activity["company"], parsed_report)
    today_str = activity["today_qty"] if activity["today_qty"] not in (None, 0) else "-"
    plan_str = activity["plan_total_qty"] if activity["plan_total_qty"] not in (None, 0) else "-"
    return (
        f"회사: {activity['company']} (공종 {activity['trade']})\n"
        f"작업: {activity['work_content']}\n"
        f"단위: {activity['unit']}  |  금일실적: {today_str}  |  계획 총수량: {plan_str}\n"
        f"[BP사 단위 컨텍스트]\n{bp_ctx}"
    )


def resolve_wa(
    activity: Activity,
    l6_choice: str,
    cand_pool: list[tuple[str, str]],
    parsed_report: ParsedDailyReport | None,
    chosen_wa: str | None = None,
) -> WAResolution:
    """WA 결정 4단계 (mapping-layer.md §4) + Task 4 fallback.

    cand_pool 빈 시 (BP master 미등록 BP사) → chosen_wa (LLM 선택 후보의 WA)
    를 그대로 채택 + source='auto_chroma_top1'. 사용자 명시 설계 의도
    "work_area + l6 가 주 매칭 키, BP 는 보조 메타데이터".
    """
    # Task 4 — cand_pool 빈 시 (BP master 미등록) — Chroma 선택 결과 그대로
    if not cand_pool:
        return WAResolution(value=chosen_wa, source="auto_chroma_top1")

    # 1단계 — BP scope WA 단일
    bp_wa = {wa for wa, _ in cand_pool}
    if len(bp_wa) == 1:
        return WAResolution(value=next(iter(bp_wa)), source="auto_bp_single")

    # 2단계 — L6 결정 후 그 L6 의 WA 단일
    l6_wa = {wa for wa, l6 in cand_pool if l6 == l6_choice}
    if len(l6_wa) == 1:
        return WAResolution(value=next(iter(l6_wa)), source="auto_l6_single")

    # 3단계 — 시트1 BPSummary.zone 으로 wa 결정 (mapping-layer.md §4 3단계).
    # 사용자 의도: "1번 시트 내용에 cub인지 fab인지 알 수 있으니 매핑에 써야 함".
    # 정책: 같은 BP사가 시트1 에 출력한 distinct zone set 과 l6_choice 의 cand_pool
    # wa set 의 교집합이 정확히 1개일 때만 채택. 교집합 0 또는 2 이상이면 4단계.
    if parsed_report is not None:
        zones_in_sheet1 = {
            s["zone"]
            for s in parsed_report["bp_summaries"]
            if s["company"] == activity["company"] and s["zone"]
        }
        cand_wa_at_l6 = {wa for wa, l6 in cand_pool if l6 == l6_choice}
        intersect = zones_in_sheet1 & cand_wa_at_l6
        if len(intersect) == 1:
            return WAResolution(value=next(iter(intersect)), source="auto_sheet1_text")

    # 4단계 — H-i-L 강제
    return WAResolution(value=None, source="hil_required")


@dataclass
class MapperConfig:
    """Mapper 6단계 호출에 필요한 환경."""

    azure_endpoint: str
    azure_api_key: str
    azure_api_version: str
    llm_model: str
    embedding_model: str
    postgres_url: str
    chroma_host: str
    chroma_port: int
    chroma_ssl: bool = False
    top_k: int = 15
    max_candidates: int = 8
    conf_threshold: float = 0.7


async def map_activity(
    activity: Activity,
    parsed_report: ParsedDailyReport | None,
    cfg: MapperConfig,
    bp_cand_lookup: dict[str, list[tuple[str, str]]] | None = None,
) -> Activity:
    """6단계 흐름 (mapping-layer.md §3).

    ① BP filter (PG) → ② 임베딩 input (단순) → ③ Chroma Top-K → BP filter ∩
    → ④ LLM input (풍부) → ⑤ LLM 분류 → ⑥ WA 결정 4단계.

    bp_cand_lookup: mapper_node 가 미리 batch fetch 한 {company: cand_pool} 캐시.
    전달 시 PG fetch skip (병렬 호출 시 tunnel connection 한계 회피).
    """

    client = AzureOpenAI(
        api_key=cfg.azure_api_key,
        api_version=cfg.azure_api_version,
        azure_endpoint=cfg.azure_endpoint,
    )

    # ① BP filter — PG (soft hint 로만 사용, Task 4 옵션 C)
    # cache lookup 우선 → 없으면 PG fetch (back-compat)
    if bp_cand_lookup is not None:
        cand_pool: list[tuple[str, str]] = bp_cand_lookup.get(activity["company"], [])
    else:
        pg = PGClient(cfg.postgres_url)
        await pg.connect()
        try:
            cand_rows = await pg.fetch_bp_candidates(activity["company"])
        finally:
            await pg.close()
        cand_pool = [(r["wa"], r["l6_main"]) for r in cand_rows]
    cand_pool_set = set(cand_pool)
    # Task 4 — cand_pool 빈 시에도 매핑 진행. BP 는 보조 메타데이터일 뿐.
    # 사용자 명시: "work_area와 l6에 주로 매칭하고 bp는 추가로 도와주는 메타데이터"

    # ② 임베딩 input (단순)
    embed_text = build_embedding_input(activity)
    emb_resp = client.embeddings.create(model=cfg.embedding_model, input=[embed_text])
    inp_vec = emb_resp.data[0].embedding

    # ③ Chroma Top-K — 전체 후보 유지 (BP filter ∩ 안 함, Task 4)
    chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
    coll = chroma.get_or_create_wbs_master()
    chroma_result = coll.query(
        query_embeddings=[inp_vec],
        n_results=cfg.top_k,
        include=["documents", "metadatas"],
    )
    candidates: list[dict[str, Any]] = []
    for i, _doc_id in enumerate(chroma_result["ids"][0]):
        meta = chroma_result["metadatas"][0][i]
        key = (meta["wa"], meta["l6_main"])
        candidates.append(
            {
                "key": key,
                "doc_text": chroma_result["documents"][0][i],
                "is_bp_registered": key in cand_pool_set,  # Task 4 soft hint
            }
        )
        if len(candidates) >= cfg.max_candidates:
            break

    # Edge case: Chroma 가 빈 결과 반환 (불가능에 가까우나 방어) → HIL
    if not candidates:
        return {
            **activity,
            "wa": None,
            "l6_main": None,
            "mapping_source": "hil_required",
            "mapping_conf": 0.0,
            "requires_review": True,
        }

    # ④ LLM input (풍부)
    llm_text = build_llm_input(activity, parsed_report)

    # ⑤ LLM 분류 — ★ 마크 = 이 BP사가 마스터에 등록된 (WA, L6) (soft hint, 가산점)
    cand_str = "\n".join(
        f"[{i}] {'★ ' if c['is_bp_registered'] else '  '}{c['doc_text']}" for i, c in enumerate(candidates)
    )
    user_msg = (
        f"작업일보 1행을 WBS 매핑 후보 중 1개로 분류.\n"
        f"★ = 이 BP사가 마스터에 등록된 (WA, L6) 조합 (가산점, 단 절대 기준 X).\n"
        f"BP 미등록이라도 work_area + L6 매칭이 자연스러우면 선택 가능.\n\n"
        f"### 작업일보 + BP사 컨텍스트\n{llm_text}\n\n"
        f"### 후보\n{cand_str}\n\n"
        f"### 응답 (JSON only)\n"
        f'{{"choice": <int>, "confidence": <0.0~1.0 float>, "reason": "<짧게>"}}'
    )
    chat_resp = client.chat.completions.create(
        model=cfg.llm_model,
        messages=[
            {
                "role": "system",
                "content": "건설 작업일보 ↔ WBS 매핑 분류기. 한국어 응답.",
            },
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    try:
        llm_result = json.loads(chat_resp.choices[0].message.content)
    except (json.JSONDecodeError, TypeError):
        return {
            **activity,
            "wa": None,
            "l6_main": None,
            "mapping_source": "hil_required",
            "mapping_conf": 0.0,
            "requires_review": True,
        }

    choice = llm_result.get("choice", -1)
    if not (0 <= choice < len(candidates)):
        return {
            **activity,
            "wa": None,
            "l6_main": None,
            "mapping_source": "hil_required",
            "mapping_conf": 0.0,
            "requires_review": True,
        }

    chosen_key = candidates[choice]["key"]
    confidence = float(llm_result.get("confidence", 0.0))

    # ⑥ WA 결정 4단계 + Task 4 fallback (chosen_wa 전달)
    wa_result = resolve_wa(
        activity,
        l6_choice=chosen_key[1],
        cand_pool=cand_pool,
        parsed_report=parsed_report,
        chosen_wa=chosen_key[0],
    )

    requires_review = confidence < cfg.conf_threshold or wa_result.source == "hil_required"

    return {
        **activity,
        "wa": wa_result.value,
        "l6_main": chosen_key[1],
        "mapping_conf": confidence,
        "mapping_source": wa_result.source,
        "requires_review": requires_review,
    }


async def _prorate_mh(
    mapped: list[Activity],
    parsed_report: ParsedDailyReport,
    pg: PGClient,
) -> list[Activity]:
    """(company, l6_main) 단위 BP사 총 인원 분배 — 옵션 X 알고리즘.

    Spec docs/superpowers/specs/2026-05-16-cpia-downstream-agents-design.md §3.
    """
    bp_total: dict[str, int] = defaultdict(int)
    for s in parsed_report["bp_summaries"]:
        bp_total[s["company"]] += s["today_incr_total"]

    bp_l6: dict[str, set[str]] = defaultdict(set)
    for a in mapped:
        if a["l6_main"] is not None:
            bp_l6[a["company"]].add(a["l6_main"])

    workers_lookup: dict[tuple[str, str], float] = {}
    for company, l6_set in bp_l6.items():
        total_n = bp_total.get(company, 0)
        if total_n == 0 or not l6_set:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = 0.0
            continue

        l6_mh: dict[str, int] = await pg.fetch_l6_plan_mh_map(company, list(l6_set))

        sum_mh = sum(l6_mh.values())
        if sum_mh == 0:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = total_n / len(l6_set)
        else:
            for l6, mh in l6_mh.items():
                workers_lookup[(company, l6)] = total_n * mh / sum_mh

    out: list[Activity] = []
    for a in mapped:
        if a["l6_main"] is not None:
            key = (a["company"], a["l6_main"])
            a = {
                **a,
                "assigned_workers": workers_lookup.get(key, 0.0),
                "worker_source": "mh_prorated",
            }
        out.append(a)
    return out
