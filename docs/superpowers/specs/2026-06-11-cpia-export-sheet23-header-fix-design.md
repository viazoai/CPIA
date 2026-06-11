# Export 통합작업일보 시트2·3 헤더 복원 + 유령열 제거 + 전 날짜 re-bake — 설계

**작성일:** 2026-06-11
**브랜치:** main (워킹트리 — PoC 미커밋 `exporter.py` 수정 보유)
**상태:** 설계 (PoC 실물 검증 완료, 사용자 승인 "딱 이거야")

---

## 1. 문제 (전부 실 파일·실 DB 검증)

UI 엑셀 다운로드(`/api/export?date=` → FastAPI `/export/run`)는 `consolidated_reports` 캐시 hit 시 **구워둔 바이트를 그대로 반환**한다(캐시 miss여야 즉석 `render_xlsx`). 9/25·9/24 모두 캐시 존재 → 코드만 고쳐선 기존 다운로드가 안 바뀌고 **re-bake 필요**.

사용자 보고 3건, 근본원인:

### (P1) 시트2·3 "주간/야간/합계" 서브헤더 누락
원본 통합작업일보 시트2·3은 헤더 **3행**(r3 제목 + r4 블록헤더 + **r5 서브헤더**), r5 = 좌측라벨 + `조출|주간|연장|야간|철야|누계`(×3블록). 현재 템플릿 `consolidated_template.xlsx`은 **r5 서브헤더 행이 통째로 누락**돼 있고, 익스포터 전역 `DATA_START_ROW=5`라 데이터가 r5(서브헤더 자리)부터 채워짐 → 서브헤더 안 보임.

### (P2) 맨 오른쪽 빈 테두리 열(시트2·3 Y열/25)
`_dedup_and_border` 가 시트2·3에 `c1=25`까지 테두리를 긋지만 `_fill_occupation/_fill_equipment` 는 col24까지만 채움 → **Y열(25) = 값 0, 테두리만**(시트2 88행·시트3 136행). 검증: `col25 값행=0 테두리행=88/136`. 원본의 'Y5=최종' 라벨이 누락돼 헤더 없는 유령 열이 됨. (시트4는 Q=비고가 끝, R부터 깨끗 — 유령열은 **시트2·3만**.)

→ P1·P2는 **같은 뿌리**: 시트2·3 r5 서브헤더 행 누락 + 전역 시작행이 시트2·3에만 한 칸 어긋남.

### (P3) 9/24 이전이 9/25와 다른 스키마로 나옴
`consolidated_reports` 검증:
- **9/25**: `is_mock=False`, `generated_at=2026-06-10 03:16` — 실 파이프라인 런이 **현재 코드**로 구움 → 시트1='1.작업사항'(rename), 직종·장비 채워짐.
- **9/24 이전(8/17~9/24)**: `is_mock=True`, `generated_at=2026-06-04 03:57` — `seed_dummy_year` 백필이 **옛 코드**로 구움 → 시트1='1.출력인원 현황'(rename 전), 직종·장비 시트 빈 껍데기(synthetic 시드는 물량만 생성).

→ 6일 차이 **다른 코드 × 다른 생성기 × 다른 데이터**. 둘 다 캐시라 코드 수정 후 **전 날짜 re-bake** 로 스키마 통일 필요.

---

## 2. 결정 (사용자 확정)

| # | 결정 | 근거 |
|---|---|---|
| D1 | 시트2·3 r5 서브헤더 복원 (조출/주간/연장/야간/철야/누계 ×3 + 좌측 라벨), **헤더는 코드(익스포터)가 작성** (옵션2) | r3·r4와 동일 룩, 바이너리 템플릿 diff 없음, grep 가능. 출력은 옵션1과 동일 |
| D2 | 시트2·3 **최종(Y/25) 열 완전 제거** (테두리 c1=24, 라벨 미작성) | 'O/X' 마커 데이터 소스 없음. 사용자 "최종 열 완전 제거" |
| D3 | 시트별 데이터 시작행: 시트1·4=r5, **시트2·3=r6** | 원본 구조(시트2·3만 헤더 3행)와 일치 |
| D4 | **전 캐시 날짜(8/17~9/25) re-bake**, `is_mock` 플래그 보존 | "24일거도 다 통일성 있게". 시드 날짜 시트2·3은 데이터 없어 헤더만 — 인지·수용됨 |

비목표(YAGNI): 최종열 'O' 마커 산식, synthetic 시드에 직종·장비 데이터 생성, 템플릿 바이너리 재작성.

---

## 3. 컴포넌트 변경

### 3.1 `pipeline/agents/exporter.py` (PoC로 검증 완료)
- `_GROUP_SHEETS`: 시트2·3 `c1` 25→**24** (최종열 테두리 제거).
- `_DATA_START = {"2.직종별 인원현황": 6, "3.장비현황": 6}` + `_data_start(title)` 헬퍼 (기본 5).
- `_unhide_and_clean(ws, n, start)`: 행 처리범위·`freeze_panes=f"A{start}"` 를 시작행 기반.
- `_dedup_and_border(ws, n, c0, c1, key_cols, start)`: `r = start + i`.
- `_unmerge_data_region`: 시트별 `_data_start(title)` 로 데이터구역 산정.
- `_fill_occupation/_fill_equipment(..., *, start)`: `r = start + i`.
- 신규 `_write_subheaders(wb)`: 시트2·3 r5에 좌측 라벨(시트별) + `조출/주간/연장/야간/철야` + 블록별 누계(`Cum. T`/`Incr. T`/`Cum. T`), B4 셀 서식 복제. **최종(Y) 미작성.**
- `render_xlsx`: `_unmerge_data_region` → `_write_subheaders` → fill(시트2·3은 `start=_data_start(...)`) → `_finalize_layout`.

시트1·4 경로(`_fill_output_manpower`·`_fill_quantity`·`_polish_sheet1`)는 `DATA_START_ROW=5` 그대로 — 무회귀.

### 3.2 테스트 (`pipeline/tests/test_exporter_*.py`)
- **갱신**: `test_finalize_sheet2_no_hidden_no_filter_white` 의 `freeze_panes == "A5"` → **"A6"** (시트2 헤더 3행).
- **추가**: 시트2·3 r5에 `주간`·`야간`·`Cum. T` 라벨 존재 + 좌측 라벨(`Dis`/`협력업체`); 데이터 r6 시작; **col25(Y) 값·테두리 0**; 시트1·4 r5 시작 무회귀.

### 3.3 re-bake 스크립트 (D4)
`consolidated_reports` 전 캐시 (site, date) 순회 → `fetch_sheet_data(pg, site, date)` → `render_xlsx(수정본)` → `upsert_consolidated_report(...)` 로 UPSERT 후 **기존 `is_mock` 보존**. 결정론(LLM 없음)이라 idempotent·재실행 안전. 9/25=is_mock False, 나머지 True 보존.
- 기존 `seed_dummy_year._backfill_consolidated_reports` 는 is_mock=TRUE 고정이라 9/25엔 부적합 → 기존값 보존하는 별도 재생성 루틴 사용(스크립트 신규 또는 기존 확장은 플랜에서 확정).
- **풋건 주의**: `upsert_consolidated_report` 는 INSERT 시 `is_mock` 을 쓰지 않아 기본 FALSE로 들어간다. 따라서 re-bake 는 **(a) UPSERT 전에 기존 행의 `is_mock` 을 읽어두고 → 렌더·UPSERT 후 그 값으로 조건부 `UPDATE`**, 또는 동등한 방식으로 원래 플래그를 복원해야 한다. (실 PoC 검증 site_id = `m15x-ph3-ibl`.)

---

## 4. 데이터 흐름

```
[수정 exporter.py] ─ render_xlsx(시트별 시작행 + r5 서브헤더 + c1=24)
        │
        ├─(런타임) consolidated_xlsx_node → 신규 업로드 시 자동 정상 스키마
        └─(일괄)   re-bake 스크립트 → 전 캐시 날짜 UPSERT(is_mock 보존)
                          │
                   consolidated_reports (homelab PG, 공유)
                          │
        /export/run → 캐시 반환 → /api/export → 브라우저 다운로드
```

## 5. 에러/리스크
- **공유 PG 일괄 쓰기**: re-bake 가 homelab `consolidated_reports` 전 날짜 UPSERT. 결정론·재실행 가능이라 롤백 불필요(소스 데이터 불변이면 동일 결과). 실행 전 행수 확인, 실행 후 9/25·9/24 재추출 대조.
- **병행 세션**: 워킹트리 공유 — `exporter.py`·테스트·스크립트만 add, 미추적 data/recipe 파일 미접근.
- **시드 날짜 시트2·3 공백**: D4로 헤더만, 데이터 없음 — 수용된 결과(시드 한계).

## 6. 검증 (Done 정의)
1. 단위 테스트 green (갱신 1 + 추가 N).
2. re-bake 후 PG(site_id=`m15x-ph3-ibl`)에서 9/25·9/24 xlsx 재추출 → 시트2·3 r5 서브헤더 존재 + col25 공백 + 시트1='1.작업사항' 통일 (실 openpyxl 덤프 원문 인용).
3. 전 캐시 날짜 byte_size 재생성 확인(0건 누락).
