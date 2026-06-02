from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["bp_summary", "job", "equip", "activity"]

# Pass2 추출에 반드시 매핑돼야 하는 필드 (미매핑 시 Tier3 안전망)
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "bp_summary": ("bp_company", "scope", "work_today", "today_incr_total"),
    "job": ("trade", "bp_company", "disc_code", "job_type"),
    "equip": ("trade", "bp", "equip_big"),
    "activity": ("trade", "bp", "work_content", "unit", "today_qty"),
}


@dataclass
class SheetRecipe:
    sheet_name: str
    columns: dict[str, int]
    timeshift_blocks: dict[str, int]  # block_name -> 조출(첫칸) col_start
    group_boundary: str  # "mm01_anchor" | "col30_merge" | "bp_company_pair" | "equip_triple" | "unknown"
    header_rows: tuple[int, int]
    final_flag_col: int | None = None


@dataclass
class FormatRecipe:
    fingerprint: str
    format_class: Literal["통합", "업체", "unknown"]
    sheets: dict[str, SheetRecipe] = field(default_factory=dict)
    generated_by: Literal["deterministic", "llm", "human"] = "deterministic"
    confidence: float = 1.0
