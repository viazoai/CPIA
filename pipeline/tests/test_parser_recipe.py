from __future__ import annotations

import openpyxl
from openpyxl import load_workbook
from pipeline.agents.parser import parse_daily_report
from pipeline.agents.recipe.bpcode import is_bp_code_v2, looks_like_code_no_korean
from pipeline.agents.recipe.extract import (
    extract_sheet1,
    extract_sheet2,
    extract_sheet3,
    extract_sheet4,
)
from pipeline.agents.recipe import parse_with_recipe
from pipeline.agents.recipe.fingerprint import fingerprint
from pipeline.agents.recipe.model import FormatRecipe, SheetRecipe, REQUIRED_FIELDS
from pipeline.agents.recipe.recognize import load_cached_recipe, recognize_format, save_recipe
from pipeline.agents.recipe.synonyms import field_for_header, role_for_sheet

UNI = "docs/sample/통합작업일보_M15X Ph-3 IBL PJT 작업일보_20250925.xlsx"
BP = "docs/sample/업체작업일보_M15X_PH4_041_M15X_PH4_UT_ 중원엔지니어링_UT배관공사_FAB_250917.xlsx"


def test_recipe_model_construct():
    sr = SheetRecipe(
        sheet_name="4.물량",
        columns={"work_content": 7, "unit": 8, "today_qty": 11, "trade": 4, "bp": 5},
        timeshift_blocks={},
        group_boundary="bp_company_pair",
        header_rows=(3, 4),
        final_flag_col=None,
    )
    fr = FormatRecipe(
        fingerprint="abc",
        format_class="업체",
        sheets={"activity": sr},
        generated_by="deterministic",
        confidence=1.0,
    )
    assert fr.sheets["activity"].columns["today_qty"] == 11
    assert "today_qty" in REQUIRED_FIELDS["activity"]


def test_fingerprint_distinguishes_and_is_stable():
    wb_u = openpyxl.load_workbook(UNI, data_only=True)
    wb_b = openpyxl.load_workbook(BP, data_only=True)
    fu1 = fingerprint(wb_u)
    fu2 = fingerprint(wb_u)
    fb = fingerprint(wb_b)
    assert fu1 == fu2  # 같은 wb 두 번 → 동일 (결정성)
    assert fu1 != fb  # 통합 vs 업체 → 다름
    assert len(fu1) == 64  # sha256 hex
    wb_u.close()
    wb_b.close()


def test_synonyms_map_headers_and_sheets():
    assert field_for_header("금일실적") == "today_qty"
    assert field_for_header("당일실적") == "today_qty"  # V2 동의어
    assert field_for_header("대표물량_작업내용") == "work_content"
    assert field_for_header("작업내용") == "work_content"
    assert field_for_header("BP사") == "bp"
    assert field_for_header("업체명") == "company_col"
    # sheet2/3 필수필드 (실측 헤더)
    assert field_for_header("관리자/근로자") == "disc_code"  # sheet2 col4 (Mm01 앵커)
    assert field_for_header("직종") == "job_type"  # sheet2 col6
    assert field_for_header("대분류") == "equip_big"  # sheet3 col4
    assert field_for_header("중분류") == "equip_mid"
    assert field_for_header("규 격") == "equip_spec"  # _norm_header 가 공백 제거 → "규격"
    # sheet1 작업텍스트 (헤더에 날짜 brackets 붙음 → substring)
    assert field_for_header("전일 작업사항 [09/24]") == "work_prev"
    assert field_for_header("금일 작업사항 [09/25]") == "work_today"
    assert field_for_header("명일 작업사항 [09/26]") == "work_tomorrow"
    assert field_for_header("ZZZ알수없음") is None
    assert role_for_sheet("4.물량") == "activity"
    assert role_for_sheet("물량집계") == "activity"  # V1 시트명 변이 alias
    assert role_for_sheet("1.출력인원 현황") == "bp_summary"
    assert role_for_sheet("2.직종별 인원현황") == "job"
    assert role_for_sheet("3.장비현황") == "equip"


def test_recognize_integrated_format():
    wb = openpyxl.load_workbook(UNI, data_only=True)
    r = recognize_format(wb)
    assert r.format_class == "통합"
    assert r.generated_by == "deterministic"
    assert r.confidence == 1.0
    # sheet4 컬럼 (통합 실측: company_col=6 이 있어 이후 1칸 우측 시프트)
    # trade=4 bp=5 company_col=6 scope=7 work_content=8 unit=9 today_qty=12
    a = r.sheets["activity"]
    assert a.columns["trade"] == 4 and a.columns["bp"] == 5
    assert a.columns["company_col"] == 6 and a.columns["work_content"] == 8
    assert a.columns["unit"] == 9 and a.columns["today_qty"] == 12
    # sheet2 final_flag 존재(통합)
    assert r.sheets["job"].final_flag_col == 25
    # sheet2 timeshift (실측: today_cum block 첫칸 col19)
    assert r.sheets["job"].timeshift_blocks["today_cum"] == 19
    # sheet3 final_flag 도 통합은 'O' 게이트 존재 (실측 col25)
    assert r.sheets["equip"].final_flag_col == 25
    wb.close()


def test_recognize_vendor_format():
    wb = openpyxl.load_workbook(BP, data_only=True)
    r = recognize_format(wb)
    assert r.format_class == "업체"
    a = r.sheets["activity"]
    assert "company_col" not in a.columns  # 업체는 업체명 컬럼 없음
    assert a.columns["work_content"] == 7 and a.columns["today_qty"] == 11
    assert r.sheets["job"].final_flag_col is None  # 업체는 'O' 게이트 없음
    wb.close()


def test_bp_code_v2_accepts_variants():
    # 기존 통합/업체 (회귀)
    assert is_bp_code_v2("PH_X-088")
    assert is_bp_code_v2("M15X_PH4_041")
    # P1 변종 — 누출 차단 대상
    assert is_bp_code_v2("M15X-PH4-041")  # dash
    assert is_bp_code_v2("M15X_PH4_041A")  # trailing suffix
    # 회사명은 코드 아님
    assert not is_bp_code_v2("중원엔지니어링")
    assert not is_bp_code_v2("협력업체01")


def test_leak_guard_flags_ascii_only_codeish():
    # 한글 0글자 + 코드 모양 → 회사명 아님 (격리 대상)
    assert looks_like_code_no_korean("ABC-2025-001")
    assert not looks_like_code_no_korean("중원엔지니어링")
    assert not looks_like_code_no_korean("Hyundai E&C")  # 공백 포함 영문 회사명 — 코드 모양 아님


def _activities_via_recipe(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb)
    acts = extract_sheet4(wb[r.sheets["activity"].sheet_name], r.sheets["activity"])
    wb.close()
    return acts


def test_sheet4_equiv_integrated():
    golden = parse_daily_report(UNI)["activities"]
    got = _activities_via_recipe(UNI)
    assert len(got) == len(golden) == 1193
    assert got == golden  # dict 완전 일치


def test_sheet4_equiv_vendor():
    golden = parse_daily_report(BP)["activities"]
    got = _activities_via_recipe(BP)
    assert len(got) == len(golden) == 33
    assert got == golden


def _bp_via_recipe(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb)
    out = extract_sheet1(wb[r.sheets["bp_summary"].sheet_name], r.sheets["bp_summary"])
    wb.close()
    return out


def test_sheet1_equiv_integrated():
    golden = parse_daily_report(UNI)["bp_summaries"]
    got = _bp_via_recipe(UNI)
    assert len(got) == len(golden) == 99
    assert got == golden


def test_sheet1_equiv_vendor_company():
    got = _bp_via_recipe(BP)
    assert {s["company"] for s in got} == {"중원엔지니어링"}  # 누출 0, 정규화 OK


def test_sheet2_equiv():
    for path, n in [(UNI, 975), (BP, 76)]:
        golden = parse_daily_report(path)["job_allocations"]
        wb = openpyxl.load_workbook(path, data_only=True)
        r = recognize_format(wb)
        got = extract_sheet2(wb[r.sheets["job"].sheet_name], r.sheets["job"])
        wb.close()
        assert len(got) == len(golden) == n
        assert got == golden


def test_sheet3_equiv():
    for path, n in [(UNI, 1111), (BP, 68)]:
        golden = parse_daily_report(path)["equipment_allocations"]
        wb = openpyxl.load_workbook(path, data_only=True)
        r = recognize_format(wb)
        got = extract_sheet3(wb[r.sheets["equip"].sheet_name], r.sheets["equip"])
        wb.close()
        assert len(got) == len(golden) == n
        assert got == golden


def test_full_report_equiv_both_formats():
    for path in (UNI, BP):
        golden = parse_daily_report(path)
        got = parse_with_recipe(path)
        for key in (
            "activities",
            "bp_summaries",
            "job_allocations",
            "equipment_allocations",
            "report_date",
            "project",
            "worker_outputs",
            "report_meta",
        ):
            assert got[key] == golden[key], f"{path} {key} 불일치"


def test_company_mismatch_sets_review():
    demo = "data/demo_inputs/20250925/업체작업일보_M15X_PH3_남웅건설_단열공사_20250925.xlsm"
    got = parse_with_recipe(demo)
    assert {a["company"] for a in got["activities"]} == {"중원엔지니어링"}  # 셀 SSOT, 덮어쓰기 X
    assert all(a["requires_review"] for a in got["activities"])  # 셀 company 가 파일명에 없음 → 전부 review


def test_recipe_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.agents.recipe.recognize.RECIPE_CACHE_DIR", tmp_path)
    wb = openpyxl.load_workbook(BP, data_only=True)
    r = recognize_format(wb)
    wb.close()
    save_recipe(r)
    loaded = load_cached_recipe(r.fingerprint)
    assert loaded is not None
    assert loaded.format_class == r.format_class
    assert loaded.sheets["activity"].columns == r.sheets["activity"].columns
    assert loaded.sheets["job"].header_rows == r.sheets["job"].header_rows  # tuple 복원
    assert isinstance(loaded.sheets["job"].header_rows, tuple)


class _MockLLM:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self.payload


def _make_activity_gap_wb(tmp_path):
    # 업체 파일의 activity 시트 work_content 헤더를 미인식 문자열로 바꿔 Tier1 gap 유발
    wb = load_workbook(BP)
    # recognize 로 activity 시트명/헤더행/work_content 컬럼을 실측해 그 헤더 셀을 깨뜨림
    probe = openpyxl.load_workbook(BP, data_only=True)
    r0 = recognize_format(probe, use_cache=False)
    a = r0.sheets["activity"]
    wc_col = a.columns["work_content"]
    ws = wb[a.sheet_name]
    # 헤더행(3,4) 중 work_content 헤더가 있는 행을 gibberish 로 치환
    for hr in a.header_rows:
        ws.cell(hr, wc_col).value = "ZZZUNKNOWN"
    probe.close()
    out = tmp_path / "gap.xlsx"
    wb.save(out)
    return str(out), wc_col


def test_tier2_broken_header_yields_tier1_gap(tmp_path, monkeypatch):
    # llm 없이 Tier1 만: work_content gap → deterministic + confidence<1.0 (fallback 가 진짜 발동함을 증명)
    monkeypatch.setattr("pipeline.agents.recipe.recognize.RECIPE_CACHE_DIR", tmp_path)
    path, wc_col = _make_activity_gap_wb(tmp_path)
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb, use_cache=False)
    wb.close()
    assert r.generated_by == "deterministic"
    assert r.confidence < 1.0
    assert "work_content" not in r.sheets["activity"].columns


def test_tier2_llm_fills_gap_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.agents.recipe.recognize.RECIPE_CACHE_DIR", tmp_path)
    path, wc_col = _make_activity_gap_wb(tmp_path)
    payload = '{"activity": {"work_content": %d}}' % wc_col

    wb1 = openpyxl.load_workbook(path, data_only=True)
    m1 = _MockLLM(payload)
    r1 = recognize_format(wb1, use_cache=False, llm_client=m1)
    wb1.close()
    assert m1.calls == 1
    assert r1.generated_by == "llm"
    assert r1.sheets["activity"].columns["work_content"] == wc_col

    # 결정성: 같은 입력 2회 → 동일 컬럼맵
    wb2 = openpyxl.load_workbook(path, data_only=True)
    m2 = _MockLLM(payload)
    r2 = recognize_format(wb2, use_cache=False, llm_client=m2)
    wb2.close()
    assert r1.sheets["activity"].columns == r2.sheets["activity"].columns


def test_tier2_bad_json_no_cache_poisoning(tmp_path, monkeypatch):
    # LLM 이 JSON 파싱 실패 응답 → gap 그대로. generated_by 는 llm 아님, 캐시 파일도 안 생김
    # (gappy recipe 를 llm 으로 캐시하면 다음 실행이 Tier3 안전망을 영구 우회 = 조용한 오염).
    monkeypatch.setattr("pipeline.agents.recipe.recognize.RECIPE_CACHE_DIR", tmp_path)
    path, _ = _make_activity_gap_wb(tmp_path)
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb, use_cache=False, llm_client=_MockLLM("NOT JSON{{"))
    wb.close()
    assert r.generated_by == "deterministic"  # 못 채웠으므로 llm 표기 안 함
    assert "work_content" not in r.sheets["activity"].columns
    assert not list(tmp_path.glob("*.json"))  # gappy recipe 캐시 금지


def test_tier2_non_numeric_value_no_crash(tmp_path, monkeypatch):
    # LLM 이 비숫자 컬럼값 반환 → caller 까지 crash 금지. 해당 필드 skip (Tier3 가 잔여 처리).
    monkeypatch.setattr("pipeline.agents.recipe.recognize.RECIPE_CACHE_DIR", tmp_path)
    path, _ = _make_activity_gap_wb(tmp_path)
    wb = openpyxl.load_workbook(path, data_only=True)
    r = recognize_format(wb, use_cache=False, llm_client=_MockLLM('{"activity": {"work_content": "oops"}}'))
    wb.close()
    assert "work_content" not in r.sheets["activity"].columns  # 비숫자 → skip
