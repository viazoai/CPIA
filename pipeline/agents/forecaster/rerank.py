"""Forecaster rerank — Atomizer metadata 정규화 + 가중치 rerank. 순수 함수.

Spec: docs/superpowers/specs/2026-05-16-cpia-forecaster-design.md §7

Atomizer 적재 schema (pipeline/agents/atomizer.py:45~59):
  date, run_id, company, l5_disc, l6_main, wa, unit,
  today_qty, assigned_workers, worker_source, mapping_conf,
  conditions: ",".join(list) → STRING (콤마 join)

Forecaster 추가 derive:
  productivity = today_qty / assigned_workers
  conditions   = string.split(",")  (empty → [])
"""

from __future__ import annotations

from typing import Any


def _normalize_chroma_metadata(m: dict) -> dict:
    """atomizer schema → Forecaster schema 변환. spec B-1 정정."""
    today_qty = float(m.get("today_qty", 0))
    workers = float(m.get("assigned_workers", 0))
    productivity = today_qty / workers if workers > 0 else 0.0

    conditions_raw = m.get("conditions", "")
    conditions = conditions_raw.split(",") if conditions_raw else []

    return {**m, "productivity": productivity, "conditions": conditions}


def rerank_cases(cases: list[dict]) -> list[dict]:
    """Chroma query 결과 → 정규화 + rerank.

    가중치:
      worker_source = "user_corrected" → distance × 0.7
      mapping_conf < 0.7              → distance × 1.5

    정렬 후 전체 반환. caller (agent.py) 가 [:rag_top_k] 자름.
    """
    out: list[dict[str, Any]] = []
    for c in cases:
        meta = _normalize_chroma_metadata(c["metadata"])
        score = c["distance"]
        if meta.get("worker_source") == "user_corrected":
            score *= 0.7
        if meta.get("mapping_conf", 1.0) < 0.7:
            score *= 1.5
        out.append({**c, "metadata": meta, "rerank_score": score})
    return sorted(out, key=lambda x: x["rerank_score"])
