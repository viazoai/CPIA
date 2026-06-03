"""Mapper agent — 작업일보 → WBS 매핑.

Spec: docs/schema/mapping-layer.md §3 (6단계 흐름) + §4 (WA 결정 4단계).

Task 6 (이 파일) — helper 함수 (build_embedding_input / build_llm_input /
build_bp_context / resolve_wa).
Task 7 — map_activity 통합 함수.
"""

from __future__ import annotations

import asyncio  # noqa: F401 — used by map_activity asyncio.to_thread wraps (L382/389/441)
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from openai import AzureOpenAI

from pipeline.chroma_client import ChromaClient
from pipeline.db import PGClient
from pipeline.state import Activity, BPSummary, ParsedDailyReport


# ============================================================
# Chroma wbs_master collection singleton (2026-05-20 hang fix)
# ============================================================
# map_activity 가 매 activity 마다 ChromaClient 새로 만들면 1162 × 4 동시 conn → AWS Chroma
# 의 user_identity 인증 timeout. async Lock 으로 1회 init 후 cache 공유.
_WBS_MASTER_CACHE: dict[tuple, Any] = {}
_WBS_MASTER_LOCK = asyncio.Lock()


async def _get_wbs_master_coll(cfg: "MapperConfig") -> Any:
    """ChromaClient + wbs_master collection 의 singleton getter.

    같은 (host, port, ssl) 키면 cache hit (1 init / 모든 cycle 공유).
    asyncio.Lock 으로 동시 init 경쟁 회피.
    """
    key = (cfg.chroma_host, cfg.chroma_port, cfg.chroma_ssl)
    async with _WBS_MASTER_LOCK:
        if key not in _WBS_MASTER_CACHE:
            chroma = ChromaClient(host=cfg.chroma_host, port=cfg.chroma_port, ssl=cfg.chroma_ssl)
            _WBS_MASTER_CACHE[key] = chroma.get_or_create_wbs_master()
        return _WBS_MASTER_CACHE[key]


# ============================================================
# 시간대 가중 MH 환산 (spec 2026-05-19 §3.2~3.3)
# ============================================================

_SHIFT_WEIGHTS = {
    "morning": 2.0,
    "daytime": 8.0,
    "overtime": 4.0,
    "night": 8.0,
    "all_night": 12.0,
}


def _weighted_mh_from_shift(shift_dict: dict | None) -> float:
    """시트2 workers_today_cum jsonb (TimeShiftCounts) → 가중 MH.

    spec §3.2 가중치 (조출 2 / 주간 8 / 연장 4 / 야간 8 / 철야 12) 적용.
    None / 빈 dict / 키 누락 → 0.0 처리.
    """
    if not shift_dict:
        return 0.0
    return sum(float(shift_dict.get(k, 0) or 0) * w for k, w in _SHIFT_WEIGHTS.items())


def _prorate_workers_with_mh(
    mapped: list[dict],
    parsed_report: dict,
    company_total_plan_mh: dict[str, float],
    active_l6_for_company: dict[str, set[str]],
) -> list[dict]:
    """company 단위 시간대 가중 누적 MH 산출 후 l6 비례 분배.

    spec §3.3.
    """
    company_weighted_mh: dict[str, float] = {}
    for ja in parsed_report.get("job_allocations", []):
        if ja.get("final_flag") != "O":
            continue
        c = ja.get("company")
        if c:
            mh = _weighted_mh_from_shift(ja.get("workers_today_cum"))
            company_weighted_mh[c] = company_weighted_mh.get(c, 0.0) + mh

    prorated: list[dict] = []
    for a in mapped:
        if a.get("l6_main"):
            c = a["company"]
            weighted_mh_c = company_weighted_mh.get(c, 0.0)
            company_mh = company_total_plan_mh.get(c, 0.0)
            plan_mh_val = float(a.get("plan_mh") or 0)
            n_l6 = len(active_l6_for_company.get(c, set())) if c else 0
            if company_mh > 0 and plan_mh_val > 0:
                cum_actual_mh = weighted_mh_c * (plan_mh_val / company_mh)
                prorate_method = "plan_mh"
            elif n_l6 > 0:
                cum_actual_mh = weighted_mh_c / n_l6
                prorate_method = "uniform_fallback"
            else:
                cum_actual_mh = 0.0
                prorate_method = "zero"
            a = {
                **a,
                "cum_actual_mh_today": cum_actual_mh,
                "cum_workers_today": cum_actual_mh / 8.0,
                "prorate_method": prorate_method,
            }
        prorated.append(a)
    return prorated


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
        "auto_bp_zone_match",  # 2026-05-20 fix C — BP 코드 일치 BPSummary.zone deterministic
        "auto_llm_rerank",  # 2026-05-20 옵션 A — LLM chosen_wa ∈ cand_pool
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

    # fix B (2026-05-20) — BP 코드별 분리 + zone 명시. 한 회사가 여러 BP site (FAB+CUB)
    # 운영 시 LLM 가 work_content 의 BP 와 zone 매칭 가능. 옵션 A 의 정확성 강화.
    if summaries:
        bp_lines = []
        for s in summaries:
            bp = s.get("bp_code") or "(BP 없음)"
            zone = s.get("zone") or "(미상)"
            wt = (s.get("work_text_today") or "").strip()
            wt_short = (wt[:120] + "...") if len(wt) > 120 else (wt or "(작업 미기재)")
            incr = s.get("today_incr_total") or 0
            cum = s.get("today_cum_total") or 0
            bp_lines.append(f"      - {bp} (zone={zone}): {wt_short} [Incr {incr:,}명, Cum {cum:,}명-일]")
        sheet1_block = "  · [시트1] BP 사이트별 작업 (작업 내용 보고 어느 BP 코드인지 판단):\n" + "\n".join(
            bp_lines
        )
    else:
        sheet1_block = "  · [시트1] BP 사이트 데이터 없음"

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
    bp_code = activity.get("bp_code") or "(미상)"
    return (
        f"회사: {activity['company']} / BP: {bp_code} (공종 {activity['trade']})\n"
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

    # 0단계 (fix C, 2026-05-20) — BP-zone deterministic 매칭.
    # activity.bp_code 와 일치하는 BPSummary 가 있고 그 zone 이 cand_pool 의 wa set 안에
    # 있으면 채택. LLM 의 우연 결정보다 우선. 사용자 본인 옛 POC 회상 ("시트1 에서 FAB/CUB
    # 알 수 있음") 와 정합. 예: 남웅건설 PH_X-001 (BPSummary.zone=FAB) →
    # cand_pool={(FAB, 철근콘크리트공사), (CUB, 철근콘크리트공사)} 의 FAB 채택.
    if parsed_report and activity.get("bp_code"):
        cand_wa_set = {wa for wa, _ in cand_pool}
        for s in parsed_report["bp_summaries"]:
            if s.get("bp_code") == activity["bp_code"] and s.get("zone"):
                if s["zone"] in cand_wa_set:
                    return WAResolution(value=s["zone"], source="auto_bp_zone_match")

    # 1단계 (옵션 A, 2026-05-20) — LLM rerank 의 (wa, l6) 가 cand_pool 안에 있으면 채택.
    # 사용자 push back ("scope ≠ wa, 오른쪽 작업으로 wa 판단") 정합. LLM 의 work_text + bp_ctx
    # 기반 판단을 신뢰. BP-zone 매칭이 없을 때 fallback.
    if chosen_wa and (chosen_wa, l6_choice) in cand_pool:
        return WAResolution(value=chosen_wa, source="auto_llm_rerank")

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


def _select_top_k_alternatives(candidates: list[dict[str, Any]], k: int = 3) -> list[dict[str, Any]]:
    """G23 — RAG candidate 중 score 내림차순 top-K 후보 추출.

    candidates 원소는 mapper map_activity() 안에서 만든
    {"key": (wa, l6_main), "score": float, ...}. 반환은 FE review
    페이지 dropdown 용 {wa, l6_main, score} 만 추려 jsonb 적재.
    """
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)[:k]
    return [{"wa": c["key"][0], "l6_main": c["key"][1], "score": float(c["score"])} for c in ranked]


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
    l75_conf_threshold: float = 0.7  # l7.5 선정 신뢰도 게이트 (env CPIA_L75_CONF_THRESHOLD)


# ============================================================
# l7.5 pageindex 선정 (pick_l75 + _call_l75_llm)
# ============================================================


def _call_l75_llm(client, model, work_content, l6, company, unit, candidates) -> dict:
    """l7.5 후보 중 best 선택 LLM 호출 (동기). asyncio.to_thread 로 감쌈."""
    cand_str = "\n".join(f"[{i}] {c}" for i, c in enumerate(candidates))
    user_msg = (
        f"건설 작업일보 1행을, 같은 공종(L6) 밑 세부작업(L7.5) 후보 중 가장 맞는 1개로 분류.\n"
        f"맞는 후보가 없거나 애매하면 choice=-1.\n\n"
        f"### 작업일보\n작업내용: {work_content}\n업체: {company}\n단위: {unit}\n공종(L6): {l6}\n\n"
        f"### L7.5 후보\n{cand_str}\n\n"
        f'### 응답 (JSON only)\n{{"choice": <int 또는 -1>, "confidence": <0.0~1.0>, "reason": "<짧게>"}}'
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "건설 작업일보 ↔ WBS L7.5 분류기. 한국어."},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


async def pick_l75(work_content, l6, company, unit, candidates, cfg, client=None) -> dict:
    """l6 밑 master l7.5 후보 중 best 선정. 반환 {l7_5_activity, l75_conf, l7_5_alternatives}.

    cfg=None + _call_l75_llm monkeypatch 시 client/cfg 미접근 (드라이 테스트).
    map_activity 는 이미 만든 client 를 재사용해 activity 당 2번째 AzureOpenAI 생성 회피.
    """
    if not candidates:
        return {"l7_5_activity": None, "l75_conf": 0.0, "l7_5_alternatives": []}
    if client is None and cfg is not None:
        client = AzureOpenAI(
            api_key=cfg.azure_api_key,
            api_version=cfg.azure_api_version,
            azure_endpoint=cfg.azure_endpoint,
        )
    model = cfg.llm_model if cfg is not None else None
    try:
        out = await asyncio.to_thread(
            _call_l75_llm, client, model, work_content, l6, company, unit, candidates
        )
    except Exception:
        out = {"choice": -1, "confidence": 0.0}
    ch = out.get("choice", -1)
    alts = [{"label": c, "score": 0.0} for c in candidates[:5]]
    if isinstance(ch, int) and 0 <= ch < len(candidates):
        return {
            "l7_5_activity": candidates[ch],
            "l75_conf": float(out.get("confidence", 0.0)),
            "l7_5_alternatives": alts,
        }
    return {"l7_5_activity": None, "l75_conf": 0.0, "l7_5_alternatives": alts}


async def map_activity(
    activity: Activity,
    parsed_report: ParsedDailyReport | None,
    cfg: MapperConfig,
    bp_cand_lookup: dict[str, list[tuple[str, str]]] | None = None,
    l75_cand_map: dict | None = None,
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
    # 2026-05-20: sync Azure call 을 asyncio.to_thread 로 wrap — event loop block 회피.
    # 이전 cycle hang root cause = asyncio.gather(Semaphore 4) × sync embeddings.create
    embed_text = build_embedding_input(activity)
    emb_resp = await asyncio.to_thread(
        client.embeddings.create, model=cfg.embedding_model, input=[embed_text]
    )
    inp_vec = emb_resp.data[0].embedding

    # ③ Chroma Top-K — 전체 후보 유지 (BP filter ∩ 안 함, Task 4)
    # 2026-05-20: ChromaClient singleton + sync query 를 asyncio.to_thread wrap.
    # 매 activity 마다 새 client 만들면 1162 × 4 동시 init → AWS Chroma user_identity timeout.
    coll = await _get_wbs_master_coll(cfg)
    chroma_result = await asyncio.to_thread(
        coll.query,
        query_embeddings=[inp_vec],
        n_results=cfg.top_k,
        include=["documents", "metadatas", "distances"],
    )
    candidates: list[dict[str, Any]] = []
    for i, _doc_id in enumerate(chroma_result["ids"][0]):
        meta = chroma_result["metadatas"][0][i]
        key = (meta["wa"], meta["l6_main"])
        # G23 — cosine distance → similarity score ∈ [-1, 1] (실용 [0, 1]).
        # Chroma collection 은 hnsw:space=cosine 으로 생성됨.
        dist = float(chroma_result["distances"][0][i])
        candidates.append(
            {
                "key": key,
                "doc_text": chroma_result["documents"][0][i],
                "is_bp_registered": key in cand_pool_set,  # Task 4 soft hint
                "score": 1.0 - dist,
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
    # 2026-05-20: sync Azure chat.completions 도 to_thread — Semaphore 4 deadlock 방지.
    chat_resp = await asyncio.to_thread(
        client.chat.completions.create,
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
    # 2026-05-20: LLM 응답이 "choice": null 인 경우 (모호 시 null 반환) None 안전 처리.
    if choice is None or not (0 <= choice < len(candidates)):
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

    l75 = await pick_l75(
        activity.get("work_content", ""),
        chosen_key[1],
        activity["company"],
        activity.get("unit", ""),
        (l75_cand_map or {}).get(chosen_key[1], []),
        cfg,
        client=client,
    )

    # 2026-06-02 (C5-1): 전건 HIL — 점수 무관 모든 매핑이 review UI 를 거치도록 강제.
    # mapping_conf 는 confidence 원본 그대로 반환(FE 표시). Spec §5.1 #1.
    requires_review = True

    return {
        **activity,
        "wa": wa_result.value,
        "l6_main": chosen_key[1],
        "mapping_conf": confidence,
        "mapping_source": wa_result.source,
        "requires_review": requires_review,
        # G23 — FE review dropdown 용 top-K 후보 (K=3).
        "alternatives": _select_top_k_alternatives(candidates, k=3),
        "l7_5_activity": l75["l7_5_activity"],
        "l75_conf": l75["l75_conf"],
        "l7_5_alternatives": l75["l7_5_alternatives"],
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
    # U1.A: plan_mh propagate — l6_mh 맵을 activity 단위로 보존 (EVM CPI/SPI 분모)
    plan_mh_lookup: dict[tuple[str, str], float] = {}
    for company, l6_set in bp_l6.items():
        total_n = bp_total.get(company, 0)
        if total_n == 0 or not l6_set:
            for l6 in l6_set:
                workers_lookup[(company, l6)] = 0.0
            continue

        l6_mh: dict[str, int] = await pg.fetch_l6_plan_mh_map(company, list(l6_set))

        # U1.A: fetch 한 l6_mh 값을 plan_mh_lookup 에 보존
        for l6, mh in l6_mh.items():
            plan_mh_lookup[(company, l6)] = float(mh)

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
                # U1.A: plan_mh — 맵에 없으면 0 (B.2 prorate 분모로 사용)
                "plan_mh": plan_mh_lookup.get(key, 0.0),
            }
        out.append(a)

    # company 전체 plan_mh 합 (prorate 분모)
    company_total_plan_mh: dict[str, float] = {}
    for a in out:
        c = a.get("company")
        if c and a.get("plan_mh"):
            company_total_plan_mh[c] = company_total_plan_mh.get(c, 0.0) + float(a["plan_mh"])

    # active l6 (균등 분배 fallback 용)
    active_l6_for_company: dict[str, set[str]] = defaultdict(set)
    for a in out:
        if a.get("company") and a.get("l6_main"):
            active_l6_for_company[a["company"]].add(a["l6_main"])

    prorated = _prorate_workers_with_mh(
        out,
        parsed_report,
        company_total_plan_mh,
        active_l6_for_company,
    )

    return prorated
