from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from pipeline.agents.parser import _norm_header, _resolve_sheet4_columns
from pipeline.agents.recipe.fingerprint import fingerprint
from pipeline.agents.recipe.model import REQUIRED_FIELDS, FormatRecipe, SheetRecipe
from pipeline.agents.recipe.synonyms import field_for_header, role_for_sheet

# recipe 캐시 디렉토리 (fingerprint 키). 테스트는 monkeypatch 로 tmp_path 주입.
RECIPE_CACHE_DIR = Path("data/parser_recipes")

_SHIFT_GROUP_LABELS = {  # group 라벨 토큰 -> block. 순서 중요: 긴/구체 토큰 먼저 (substring 매칭)
    "전일투입누계": "yest_cum",
    "금일투입누계": "today_cum",  # 통합 sheet3
    "전일누계": "yest_cum",
    "전일누적": "yest_cum",
    "금일누계": "today_cum",
    "금일누적": "today_cum",
    "전일투입": "yest_incr",
    "금일투입": "today_incr",
}


def _find_timeshift_blocks(ws, label_row: int, sub_row: int, max_col: int) -> dict[str, int]:
    """sub_row 에서 '조출' 첫칸을 찾아, 그 위 group 라벨로 block_start 매핑."""
    blocks: dict[str, int] = {}
    for c in range(1, max_col + 1):
        sub = _norm_header(ws.cell(sub_row, c).value)
        if sub != "조출":
            continue
        block_name = None
        for lr in (label_row, label_row - 1):
            for cc in range(c, 0, -1):
                lbl = _norm_header(ws.cell(lr, cc).value)
                hit = next((b for tok, b in _SHIFT_GROUP_LABELS.items() if tok in lbl), None)
                if hit:
                    block_name = hit
                    break
            if block_name:
                break
        if block_name and block_name not in blocks:
            blocks[block_name] = c
    return blocks


def _resolve_sheet_recipe(ws, role: str) -> tuple[SheetRecipe, list[str]]:
    max_col = ws.max_column or 0
    if role == "activity":
        cols = _resolve_sheet4_columns(ws)  # 기존 헤더해석 재사용 (회귀 안전)
        sr = SheetRecipe(ws.title, cols, {}, "n/a", (3, 4), None)
        missing = [f for f in REQUIRED_FIELDS["activity"] if f not in cols]
        return sr, missing

    hdr = (3, 4) if role == "bp_summary" else (4, 5)
    cols: dict[str, int] = {}
    for c in range(1, max_col + 1):
        for hr in hdr:
            fld = field_for_header(ws.cell(hr, c).value)
            if fld and fld not in cols:
                cols[fld] = c
    if "bp" in cols:
        cols.setdefault("bp_company", cols["bp"])
    blocks = _find_timeshift_blocks(ws, hdr[0], hdr[1], max_col)
    final_flag_col = None
    for c in range(1, max_col + 1):
        if any(
            ws.cell(r, c).value == "O" for r in range(hdr[1] + 1, min((ws.max_row or 0) + 1, hdr[1] + 200))
        ):
            final_flag_col = c
            break
    # role 미등록 시 KeyError 대신 "unknown" — Tier3 안전망(group_boundary=="unknown")이 잡도록 위임
    boundary = {"bp_summary": "col30_merge", "job": "mm01_anchor", "equip": "equip_triple"}.get(
        role, "unknown"
    )
    if role == "bp_summary":
        # 조출 블록 시작 +6 = 그룹 Total 컬럼. 통합 실측: today_incr 24→30, today_cum 31→37
        # (parse_daily_report 의 col30/col37 리터럴과 일치 — Task6~9 등가 테스트가 가드).
        if "today_incr" in blocks:
            cols["today_incr_total"] = blocks["today_incr"] + 6
        if "today_cum" in blocks:
            cols["today_cum_total"] = blocks["today_cum"] + 6
    sr = SheetRecipe(ws.title, cols, blocks, boundary, hdr, final_flag_col)
    missing = [f for f in REQUIRED_FIELDS[role] if f not in cols]
    return sr, missing


def _recipe_cache_path(fp: str) -> Path:
    return RECIPE_CACHE_DIR / f"{fp}.json"


def save_recipe(recipe: FormatRecipe) -> None:
    """recipe 를 JSON 으로 fingerprint 키 캐시에 저장. SheetRecipe 까지 재귀 직렬화."""
    RECIPE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _recipe_cache_path(recipe.fingerprint)
    path.write_text(json.dumps(asdict(recipe), ensure_ascii=False, indent=2), encoding="utf-8")


def load_cached_recipe(fp: str) -> FormatRecipe | None:
    """캐시된 recipe 로드. 파일 없거나 손상 시 None. header_rows 는 tuple 로 복원(JSON 은 tuple 없음)."""
    path = _recipe_cache_path(fp)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    sheets = {
        role: SheetRecipe(
            sheet_name=sr["sheet_name"],
            columns=sr["columns"],
            timeshift_blocks=sr["timeshift_blocks"],
            group_boundary=sr["group_boundary"],
            header_rows=tuple(sr["header_rows"]),
            final_flag_col=sr["final_flag_col"],
        )
        for role, sr in data["sheets"].items()
    }
    return FormatRecipe(
        fingerprint=data["fingerprint"],
        format_class=data["format_class"],
        sheets=sheets,
        generated_by=data["generated_by"],
        confidence=data["confidence"],
    )


def recognize_format(wb, use_cache: bool = True) -> FormatRecipe:
    fp = fingerprint(wb)
    if use_cache:
        cached = load_cached_recipe(fp)
        if cached is not None:
            return cached
    sheets: dict[str, SheetRecipe] = {}
    total_req = 0
    mapped_req = 0
    for name in wb.sheetnames:
        role = role_for_sheet(name)
        if role is None:
            continue
        sr, missing = _resolve_sheet_recipe(wb[name], role)
        sheets[role] = sr
        total_req += len(REQUIRED_FIELDS[role])
        mapped_req += len(REQUIRED_FIELDS[role]) - len(missing)
    fmt = "통합" if ("activity" in sheets and "company_col" in sheets["activity"].columns) else "업체"
    conf = (mapped_req / total_req) if total_req else 0.0
    recipe = FormatRecipe(fp, fmt, sheets, "deterministic", conf)
    # 결정론 recipe 는 매 실행 재현 가능 → 캐시 불필요(오염 방지). llm/human recipe 만 영속.
    if recipe.generated_by in ("llm", "human"):
        save_recipe(recipe)
    return recipe
