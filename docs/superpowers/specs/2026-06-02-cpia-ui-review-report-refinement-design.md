# CPIA UI 개선 — Review 탭 + 보고서 탭 정교화 Design

**작성일:** 2026-06-02
**대상:** `web/` (B_Track) 전용 — pipeline(A_Track) 무관
**데모 마감:** 2026-06-05(목)
**리뷰:** 5-렌즈 패널(feasibility·coherence·scope·design-lens·completeness) 1회전 반영 (blocker 2 + major 6 수정)

---

## Goal

데모 시연 화면 두 곳을 다듬는다.

1. **Review 탭(`/review`)** — 공종(토목/건축)을 눌러도 우측 "작업물량"이 비는 버그를 고치고, HIL 확정과 누적 등록 열람 두 의도를 데이터-트리거 토글로 자동 전환한다.
2. **보고서 탭(`/reports`)** — WP목록 컬럼을 의사결정에 맞게 재구성(지연일·단축가능일), Work Area 표기 수정, 권고사항 줄바꿈 버그 수정, 공기단축 시나리오 그래프를 동적(스크롤 줌 + 라인 클릭 강조/컴팩트 카드)으로 만들고 KPI·긴 카드 리스트를 정리한다.

## 제약 (불가침)

- **`web/` 안에서만.** pipeline/, DB 스키마 변경 없음. API 라우트는 web/ 소속이므로 수정/신규 허용.
- **디자인 수술적 변경.** 이 spec에 명시된 컬럼·KPI·인터랙션·카드·상태문구 외 layout/스타일/markup 골격은 보존.
- **한자 금지.** 코드/문서/UI 어디에도.

---

## 검증된 사실 (실 코드 file:line + 실 데이터 curl/DB)

런 `f57e8ae0-3f76-00c2-3047-c2abc8da3dd8`(status=completed), 날짜 2025-09-24, dev 5537, site `m15x-ph3-ibl`(is_mock=FALSE) 기준 실측.

### Review 탭
- `app/api/mock/review/route.ts:37-40` — `WHERE pr.site_id AND pr.status='waiting_hil_1' AND ma.requires_review=TRUE AND ma.is_mock`. 활성 run이 completed라 현재 0행. 실측: `curl /api/mock/review` → `cards:0`.
- **누적 등록 규모(실측):** site 누적 `mapper_activities` 70,890행, distinct wp_id 31개. 단일 노드도 cap을 초과 — `fab-승강기공사` 트리 total=1457, `fab-지붕공사` 732, `cub-외장판넬공사` 356 등. → **전역 LIMIT 300 한 방으로는 모든 노드를 못 덮음**(빈칸 버그 재현). 또 `run_id`는 UUID라 `ORDER BY run_id DESC`가 시간순이 아님(최신 started_at run은 `0a3f…`인데 run_id DESC 1위는 `febf…`). → 정렬은 `pipeline_runs.started_at DESC`, fetch는 **노드 단위 lazy**로 가야 함.
- `lib/transforms.ts:209-216` — `activity_agg.total_count = COUNT(*) FROM mapper_activities WHERE site_id GROUP BY (wa,l6_main)` (run 무제약 = 누적). 트리 노드의 누적 등록수 소스. `:197-207` review_agg = requires_review + trade IN('건축','토목') + today_qty>0.
- **WBS 트리 = 실제 4레벨**(transforms.ts:243-312 실측): `building(id=siteId)` → `WA(type:"trade", id="FAB")` → `l5_disc(type:"trade", id="FAB::골조", name=l5_disc)` → `work_package(type:"work_package", id=wp_id, 필드 wa·l6_main 보유)`. **주의: WA 노드와 l5_disc 노드 둘 다 `type:"trade"`** — 구분은 id의 `"::"` 유무. WBSNode에 `l5_disc` 필드는 없고 l5_disc 값은 노드 id(`"{wa}::{l5_disc}"`)에 담김. work_package만 `wa`/`l6_main` 필드 보유.
- **`ma.l5_disc` 컬럼 실재 검증:** `agent-tasks/route.ts:27`·`runs/items/route.ts:109,122,139`가 `COALESCE(ma.l5_disc, ma.trade)`로 이미 사용 중이고 라이브 Mapper API 171행 정상 반환 → A1 SQL의 `ma.l5_disc` 유효(스키마 변경 불요).
- `app/(app)/review/page.tsx:11` cards state만 존재(registered 없음). `:13` `onlyUnconfirmed=useState(true)`(하드코딩). `:18-21` fetch는 `{wbs,cards}`만 destructure. `:24-47` visibleCards(onlyUnconfirmed + selectedNode 필터). `:79-99` handleConfirmAll.
- `ReviewItem` 타입(`lib/types.ts:139-154`)은 **항상 `status:"confirmed"|"unconfirmed"` 보유**(별도 필드 없음).
- `app/components/review/ReviewCard.tsx` — `isConfirmed=item.status==="confirmed"`(:17). 확정 버튼은 `!isConfirmed`로 게이트(:90-99)되지만 **"수정" 버튼(:100-107)과 editMode 콤보(:73-87)는 status 무관 항상 렌더**. 배지 "확정"(녹색, :34-37)/"미확정"(:41-43).

### 보고서 탭
- `app/components/reports/WPSummaryTable.tsx:37-43` 헤더 `WP명·공종·BP사·Impact·Productivity·공기 단축·Status`. `:65`{wp_name}/`:67`{trade}/`:69-70`{impact}%/`:72-73`{productivity}%/`:75-83`recovery_days→`-N일`/`—`/`:42`라벨 "공기 단축".
- `wp_summary` jsonb 키(실측): …`recovery_days, risk_level, status, trade, …, wp_id, wp_name`. **`delay_days` 필드 없음**, `recovery_days` 있음.
- **wp_name 포맷(13행 전수 실측):** 전부 `"{trade} · {WA}"` (예 `"철근콘크리트공사 · CUB"`, 하이픈 trade도 `"배수 공사 · FAB"`). `wp_id="{wa}-{trade}-{company}"`(wa는 항상 첫 세그먼트, 소문자, 하이픈 없음). **검증: 13행 모두 `wp_name.split(" · ").pop()` == `wp_id.split("-")[0].toUpperCase()`.**
- per-WP 지연일 소스(실측): `optimizer.by_wp[wp_id].details`의 `"일정 영향"` 라벨 값 = `"일정 충족"` 또는 `"N일 지연"`(N∈{1,2,3,4,5}). **24개 WP 전부 라벨 존재·wp_id 100% 정합**(옵티마이저 카드와 동일 SSOT). **이 값은 BE jsonb의 wp_summary 필드가 아니라 optimizer_view_jsonb에만 있음 → FE 계산 전용.**
- `app/(app)/reports/page.tsx:143-149` filteredWpRows(visibleTrades + dead row 제외 + status). `:258-262` OptimizerResult에 `optimizer.by_wp[selectedWpId]` 전달.
- `app/components/reports/OptimizerResult.tsx` — **B5 실제 원인 재확인:** `:49` `<ul className="… list-decimal list-inside …">`, `:57` `<li>`의 **첫 자식이 블록 `<div className="text-ink">`(:58)**. `[키워드] action`은 이미 그 div 안 inline `<span>`(`:59-60`)으로 **붙어 있음**. 줄바꿈 버그의 잔존 원인은 action이 아니라 **`list-style-position:inside` 마커(1.)가 블록 div 앞에서 자체 줄을 차지** → "1." 만 한 줄, 본문은 다음 줄. (사용자 지적 "숫자하고 줄바꿈… 숫자 옆에" 정확히 일치.) 수정 대상은 `:58` 블록 div를 inline으로.

### ForecastChart / 환경
- `app/components/charts/ForecastChart.tsx:113-123` KPI "예상 공기". `:124-134` "최적화 공기". `:69-87` data 슬라이스. `:194-297` recharts ComposedChart. `:216/219/222/225` planned/actual/forecast/base 라인. `:188-191` mint 범례. `:389-433` 하단 긴 aiAdvice 카드 리스트.
- **환경:** react `^18`, react-dom `^18`, recharts `^3.8.1`(package.json 실측). recharts `<Line onClick>`은 곡선 path(fill:none)에 실제 전달됨(리뷰 소스 확인) → C4 가능.
- **React 18 wheel 주의:** React는 wheel을 root에 passive 등록 → 합성 `onWheel` 안의 `preventDefault()`는 no-op. **선례: `app/components/landing/PresentationShell.tsx:57-76`이 이미 `el.addEventListener("wheel", onWheel, {passive:false})` + cleanup 패턴 사용.** C3는 이 패턴을 따른다.
- `/tasks` Forecaster/Optimizer 카드는 `Work Area="FAB"`로 정상(실측) → "l6*wa" 이슈는 거기가 아니라 보고서 WP목록 wp_name. (손대지 않음.)

---

## 결정 (사용자 Q&A + 리뷰 반영)

| 키 | 결정 |
|----|------|
| Review 등록뷰 | **누적 등록**(site 전체 run). 단일 노드도 수천 건 → **노드 클릭 시 그 노드만 lazy fetch**(전역 캡 폐기) |
| Work Area 값 | **WA 코드만**(CUB/FAB). 도출 = `wp_name.split(" · ").pop()`, 폴백 `wp_id.split("-")[0].toUpperCase()` (13행 정합 검증) |
| 그래프 줌 | **마우스 스크롤 휠** — PresentationShell 패턴(ref + non-passive addEventListener), 더블클릭 리셋, 차트 위에서만 가로챔 |
| 라인 클릭 | **AI 시나리오(base) 라인 클릭 → 컴팩트 카드**. 강조 시 forecast/plan/band만 흐림, **현황 실적(actual)은 유지** |
| 등록 카드 | **읽기전용**(`readOnly` prop): 확정·수정 버튼+editMode+draggable 숨김, 배지 "등록" |
| 지연일 소스 | **FE 계산** — `optimizer.by_wp[wp_id].details["일정 영향"]` 파싱. BE 변경 없음. 없으면 0 |
| toggle 기본 | `cards.length>0 ? ON : OFF`. 라이브 run(waiting_hil_1)에선 ON 도달, 정적 completed run에선 OFF가 정상 |

---

## 변경 명세

### A. Review 탭

**A1. 누적 등록 — 노드 단위 lazy fetch (신규 라우트)** — `app/api/mock/review/registered/route.ts`(신규)
- `GET ?wa=<WA>&l5=<l5_disc>&l6=<l6_main>&limit=500` — 인자에 따라 site 누적 `mapper_activities` 중 해당 노드만 반환.
  - WP 노드: `wa` + `l6_main` 일치. trade 노드: `wa` + `l5_disc` 일치(l6 생략). WA 노드: `wa`만.
  ```sql
  SELECT ma.id, ma.run_id, ma.idx, ma.company, ma.today_qty, ma.unit,
         ma.wa, ma.l6_main, ma.mapping_conf, pa.work_content,
         COUNT(*) OVER() AS total
  FROM mapper_activities ma
  JOIN pipeline_runs pr USING (run_id)
  LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
  WHERE pr.site_id=${siteId} AND ma.is_mock=${useMock}
    AND ma.l6_main IS NOT NULL
    AND ma.wa=${wa}
    AND (${l6}::text IS NULL OR ma.l6_main=${l6})
    AND (${l5}::text IS NULL OR ma.l5_disc=${l5})
  ORDER BY pr.started_at DESC NULLS LAST, ma.mapping_conf DESC NULLS LAST
  LIMIT ${limit}
  ```
  - 반환 `{ items: ReviewItem[], total: number }`. 각 item은 기존 `cards` 변환과 동일(`deriveWpIdAndPath` 재사용), `status:"confirmed"`.
  - `total`로 "총 N건 중 최근 M건" 헤더 표기 → 캡 투명화(silent cap 금지). 이 `total`은 쿼리가 실제 매칭한 건수라 표시 내용과 항상 정합. (참고: 좌측 트리 배지 total_count는 `activity_agg`가 (wa,l6_main)로만 GROUP BY — WP 노드 클릭 시 헤더 N과 일치, trade 노드는 집계축이 달라 약간 다를 수 있음. WP 레벨이 정확, 데모엔 무영향.)
- 기존 `app/api/mock/review/route.ts`는 그대로 `{wbs,cards}`(pending) 반환.

**A2. 토글 초기값 데이터-트리거** — `review/page.tsx:13,18-21`
- `useState(true)` → `useState(false)`. 초기 fetch `.then` 안에서 `setOnlyUnconfirmed(cards.length>0)`. (요검토 있으면 HIL, 없으면 등록뷰.)
- **트리거는 오직 `cards.length`**(pending = `/api/mock/review`가 반환한 requires_review 건수). FE는 run.status를 직접 보지 않음 — "라이브 run"이란 그 라우트가 0행 초과를 반환하는 상태(=활성 run이 waiting_hil_1 + 저확신 매핑 존재)를 가리키는 맥락 설명일 뿐.
- A2/A3는 1줄 분기라 page.tsx 인라인 유지(헬퍼 추출 안 함 — scope 리뷰 반영).

**A3. 확정 후 자동 복귀 + 성공 피드백** — `review/page.tsx:79-99`
- `handleConfirmAll` 후 pending(미확정) 0 도달 → `setOnlyUnconfirmed(false)` + 인라인 성공 메시지 state(`confirmedNotice`, 예 "N건 확정 완료"). **렌더 위치: 우측 "작업물량" 패널 헤더(`review/page.tsx:134-140`)의 토글 옆**, 짧게 표기 후 다음 인터랙션에 사라짐(별도 모달/토스트 라이브러리 X). WBS 트리 review_count 배지는 자연히 0으로.

**A4. 토글 소스 분기 + registered state 배선** — `review/page.tsx`
- state 추가: `registered: ReviewItem[]`, `registeredTotal: number`, `registeredError: boolean`.
- **노드 → 쿼리 파라미터 도출(`nodeToQuery`, 신규 순수함수):** page.tsx의 기존 `find(wbs, selectedNodeId)`(:33-41)로 노드 객체를 얻은 뒤 노드 타입/ id로 분기.
  - `type==="work_package"` → `{ wa: node.wa, l6: node.l6_main, l5: null }` (필드 직접 보유).
  - `type==="trade"` → id에 `"::"` 있으면 l5_disc 레벨 `{ wa: id.split("::")[0], l5: id.split("::")[1], l6: null }`, 없으면 WA 레벨 `{ wa: id, l5: null, l6: null }`.
  - `type==="building"` → null(루트는 fetch 안 함).
- `onlyUnconfirmed=false` + 노드 선택 시 → `nodeToQuery`로 `/api/mock/review/registered?wa=&l5=&l6=&limit=500` fetch → setRegistered/setRegisteredTotal. (등록뷰는 노드 선택 전제 — 미선택/building 노드는 fetch 안 함.)
- fetch 실패 시 `setRegisteredError(true)` → A6에서 0건과 구분된 에러 문구. (기존 fetch에 없던 `.catch` 추가.)
- `visibleCards`(`:24-47`) 베이스: `onlyUnconfirmed ? cards : registered`. pending(cards)은 기존 client 노드필터 유지, registered는 서버가 이미 노드-스코프라 그대로.
- 데이터 계약 명시: 두 배열 모두 `ReviewItem[]` 이며 `status` 항상 존재. cards=unconfirmed(로컬 확정 시 confirmed로), registered=confirmed.

**A5. 등록 카드 읽기전용** — `ReviewCard.tsx` + `review/page.tsx`
- ReviewCard에 `readOnly?: boolean` prop 추가. `readOnly` 시: 확정 버튼·수정 버튼(:100-107)·editMode 콤보(:73-87) 미렌더, `draggable=false`, 상단 배지 "확정"→**"등록"**(중립 톤)로 텍스트만 교체.
- page.tsx에서 `<ReviewCard readOnly={!onlyUnconfirmed} … />`. (등록뷰의 모든 카드는 열람 전용.)

**A6. 빈 상태 문구 분기** — `review/page.tsx:146-150`
- HIL 모드 0건: "검토할 신규 매핑이 없습니다."
- 등록 모드 + 노드 미선택: "좌측에서 공종 또는 WP를 선택하면 누적 등록 작업을 볼 수 있습니다."
- 등록 모드 + 노드 0건: "이 공종에 등록된 작업이 없습니다."
- 등록 모드 + fetch 에러(`registeredError`): "등록 작업을 불러오지 못했습니다. 잠시 후 다시 시도하세요." (0건과 구분.)

WBSTree·토글 라벨·카드 골격/스타일 보존.

### B. 보고서 탭

**B1+B2+B4. WP목록 컬럼 재구성** — `WPSummaryTable.tsx`, `lib/types.ts`
- 최종 컬럼: **Work Area · 공종 · BP사 · 지연일 · 단축가능일 · Status**.
- `lib/types.ts` `WPSummaryRow`에 `delay_days?: number` 추가(FE-augment 필드 — BE jsonb 아님, B3에서 주입).
- 헤더 `WP명`→`Work Area`(:37), 값: WA 코드(B4 헬퍼). `Impact`(:40,69-70)·`Productivity`(:41,72-73) 컬럼 삭제. `공기 단축`(:42)→`단축 가능일`(값 `recovery_days` 그대로). 신규 `지연일`(값 `delay_days`로 `+N일`/`0일`).
- **B4 WA 헬퍼**(`lib/wp-format.ts` 신규 순수함수): `waCode(row)= (row.wp_name.includes(" · ") ? row.wp_name.split(" · ").pop()! : row.wp_id.split("-")[0].toUpperCase())`. (13행 정합 검증 완료.)

**B3. 지연일 FE 계산 + augment** — `reports/page.tsx:143-149`, `lib/wp-format.ts`
- 순수함수 `parseDelayDays(detailsArr): number` — `details`에서 `label==="일정 영향"` value를 `/(\d+)\s*일\s*지연/` 매칭→int, "일정 충족"/미매칭/항목없음→0.
- filteredWpRows 빌드 시 각 row에 `delay_days = parseDelayDays(detail.optimizer.by_wp[row.wp_id]?.details ?? [])` 주입. optimizer 엔트리 없으면 0. **BE 변경 없음.**

**B5. 권고사항 줄바꿈 수정** — `OptimizerResult.tsx:58`
- 근본 원인(재확인): `list-decimal list-inside` 마커가 블록 `<div>`(:58) 앞에서 자체 줄 차지 → 번호와 본문 분리. (action inline은 이미 적용됨 — 거기 아님.)
- 수정: `:58` `<div className="text-ink">` → `<span className="text-ink">`(inline). 마커(1.)와 `[키워드] action`이 한 줄. reason 블록(:62-66)은 아래 줄 유지. list 번호·스타일 보존.
- `text-ink`는 색상 전용 클래스(margin/padding 없음)라 span 전환에 추가 spacing 조정 불요. 마커-본문 간격은 `list-inside` 기본 + `[{r.keyword}]` 앞 공백으로 충분. 필요 시 `ml-1`만 미세 조정.
- TDD: 먼저 5537에서 줄바꿈 재현 확인 → 수정 후 마커+본문 동일 라인 단언.

### C. ForecastChart 동적화 — `ForecastChart.tsx`

**C1. 예상 공기 KPI 숨김**(:113-123) — "최적화 공기" 블록만.

**C2. 하단 긴 AI 권고 카드 리스트 제거**(:389-433) — `aiAdvice` map 블록 삭제. `aiSummaryText` 단락(:376-387)·3선 요약 테이블 유지. `aiAdvice` prop은 C4 카드에서 재사용하므로 유지.

**C3. 마우스 스크롤 줌**(:69-87,194-297) — PresentationShell 패턴 준수
- visible-window state `[viewStart,viewEnd]`(allData 인덱스). 초기 = 현행 todayIdx ±90/+240.
- `useRef`로 차트 래퍼 div 참조 + `useEffect`에서 `el.addEventListener("wheel", onWheel, {passive:false})` 등록 + cleanup. (합성 onWheel 금지 — preventDefault no-op.)
- handler: `e.preventDefault()`, 커서 X 비율 중심으로 윈도우 폭 축소/확대. clamp: 최소 14 인덱스, 최대 allData 전체.
- `data = allData.slice(viewStart,viewEnd)`(기존 마커/도메인 로직 그대로 동작).
- **더블클릭 → 초기 윈도우 리셋.** 차트 아래 보조 hint "스크롤 확대 · 더블클릭 초기화".
- **페이지 스크롤 트랩 회피:** 리스너를 window가 아닌 **차트 래퍼 div에만** 바인딩 → 커서가 차트 밖이면 페이지 정상 스크롤. (커서가 차트 위일 때만 줌 — 인터랙티브 차트 표준.)

**C4. AI 시나리오 라인 클릭 → 컴팩트 카드**(:188-191,215-225 + 신규)
- state `activeLine: "base"|null`. base `<Line onClick>` + mint 범례 항목 클릭으로 토글(`cursor-pointer`, hover 굵기). 한 번 더/카드 × 로 해제.
- **강조 위계:** activeLine="base"면 forecast·planned·band만 `strokeOpacity 0.25`로 흐림. **actual(현황 실적, 검정 굵은 선)과 base는 full 유지** — 경영진이 실적 추세를 잃지 않게.
- **cold_start 가드:** `diagnosis.scenarios.base.curve`가 비면 base 라인 미렌더/클릭 불가 → 카드 안 뜸(깨진 상태 없음).
- 컴팩트 카드(activeLine="base"일 때 그래프 아래): `recoveryDays`("N일 만에 plan 따라잡음") + 핵심 권고 1~2개(`aiAdvice` recovery_days desc top1의 recommendations.slice(0,2), 없으면 `aiSummaryText` 1줄). 작게(text-[12.5px], ring-1, max-w 제한). C2에서 뺀 정보가 여기로 압축 이동.

---

## 인터랙션 상태 정리 (구현자 추측 제거용)

| 상황 | 화면 |
|------|------|
| 진입, pending>0 | 토글 ON, HIL 카드(요검토) |
| 진입, pending=0 (정적 데모) | 토글 OFF, 등록뷰 — 노드 미선택 안내 문구 |
| "모두 확정" 클릭 후 | 성공 문구 + 토글 자동 OFF + 트리 배지 0 |
| 등록뷰, 노드 클릭 | 그 노드 누적 등록 카드(읽기전용) + "총 N건 중 최근 M건" |
| 등록뷰, 노드 0건 | "이 공종에 등록된 작업이 없습니다" |
| 그래프 줌 한계 | clamp(추가 줌 무반응), hint로 더블클릭 리셋 안내 |
| AI 시나리오 라인 클릭 | base+actual full, 나머지 0.25, 컴팩트 카드 표시 |
| base 데이터 없음(cold_start) | 라인/카드 비활성(아무 일 없음) |

## 테스트 전략 (vitest + jsdom, 기존 co-located 패턴)

순수 로직 우선. 1줄 분기(A2/A3)는 추출/단위테스트 안 함(scope 리뷰 반영).
1. `lib/wp-format.ts` — `waCode`(wp_name 경로 + 폴백), `parseDelayDays("5일 지연")===5 / "일정 충족"===0 / []===0`.
2. `WPSummaryTable` 렌더(@testing-library) — Impact/Productivity 헤더 부재, "Work Area"·"지연일"·"단축 가능일" 존재, WA값 "CUB" 렌더, delay_days `+5일`.
3. `OptimizerResult`(B5) — 1번 li 안 마커와 `[키워드]`가 동일 inline flow(구조/스냅샷 단언).
4. `ReviewCard` readOnly — `readOnly` 시 확정·수정 버튼 부재, 배지 "등록"; 아니면 버튼 존재.
5. registered API 라우트 — wa/l6 인자로 해당 노드 행만, `total` 반환(@testing 또는 curl 통합).
6. **라이브 e2e(수동, 5537):** review 등록뷰 노드 클릭 시 카드 표시(승강기공사 등 high-count 포함), confirmAll 후 등록뷰 전환, 보고서 권고 줄바꿈 해소, 스크롤 줌·더블클릭·라인클릭 카드 동작.

각 변경 작은 커밋(TDD: 실패테스트→구현→green).

## Out of Scope
- pipeline/·DB 스키마 변경(누적 등록은 기존 데이터로 충분).
- WBS 트리 total_count를 "오늘 등록"으로 바꾸기(누적이 의도값).
- `/tasks` Forecaster/Optimizer 카드(Work Area 정상).
- 권고 텍스트 내용/LLM 프롬프트, 보고서 다른 섹션(생산성 추세·4분면).
- 토스트 라이브러리 도입(인라인 성공 문구로 대체).

## 파일 영향 요약
- 신규: `web/app/api/mock/review/registered/route.ts`(A1), `web/lib/wp-format.ts`(B3,B4) + co-located 테스트
- 수정: `web/app/(app)/review/page.tsx`(A2-A4,A6), `web/app/components/review/ReviewCard.tsx`(A5), `web/app/components/reports/WPSummaryTable.tsx`(B1,B2,B4), `web/app/(app)/reports/page.tsx`(B3), `web/app/components/reports/OptimizerResult.tsx`(B5), `web/app/components/charts/ForecastChart.tsx`(C1-C4), `web/lib/types.ts`(WPSummaryRow.delay_days)
