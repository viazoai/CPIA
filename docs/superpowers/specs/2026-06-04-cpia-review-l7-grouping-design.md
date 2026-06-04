# CPIA review 우측 작업물량 카드 — l7 기준 그룹핑 설계

- 작성일: 2026-06-04
- 브랜치: `feature/review-l75-hil`
- 범위: review 페이지 우측 "작업물량" **등록(누적) 카드**의 그룹 헤더를 l7.5 → **l7** 기준으로 묶기
- 관련 결정: gbrain `decisions/cpia-review-card-grain-2026-06-04` (좌측 카드 grain = l7.5 현황유지, 별개 사안)

---

## 1. 문제 (현재 동작 — 실측 확인됨)

review 페이지 우측 "작업물량" 등록 모드에서 좌측 l6 공종(예: 철근콘크리트공사)을 선택하면, 그 아래 l7.5 작업이 **하나의 그린 헤더 아래 평면 나열**된다.

- `web/lib/review-group.ts:22` `groupCardsByWp` 가 `ai_mapped_wp_id`(= `wa-l6`) 단일 키로 묶음.
- `web/lib/review-group.ts:36` 그룹명 = `splitPath(raw[0].ai_mapped_path)` = **첫 카드의 l7.5 라벨**.
- 라이브 검증(npm dev :5537, 철근콘크리트공사 FAB): 그린 헤더 "기초공사 : 철근 콘크리트 타설" 하나 아래 47개 l7.5 카드가 거푸집/철근/콘크리트/PSRC 구분 없이 한 통에 나열됨.

사용자 의도: 그 그린 헤더를 **l7(작업 묶음)** 기준으로 나눠 보이게 한다. 예: 거푸집공사 / 철근공사 / 콘크리트공사 / PSRC공사.

## 2. PoC 근거 (실 DB·실 API, 추측 아님)

마스터(`activity_master`, site `m15x-ph3-ibl`, 건축+토목):

| grain | 컬럼 | distinct |
|---|---|---|
| l6 | `l6_main` | 17 |
| **l7** | **`l7_sub`** | **35** |
| l7.5 | `l7_5_activity` | 202 |
| leaf | `wbs_activity_id` | 689 |

- **l7 데이터는 이미 존재** — `activity_master.l7_sub` + `mapper_activities.l7_sub`. 원본 WBS 엑셀(`load_master_list.py` C_L7=18) 재적재 불필요.
- `mapper_activities.l7_sub` 채움률 = **70,890 / 71,005 (99.8%)** (건축/토목 확정행).
- 마스터 `(wa,l6,l7.5) → l7_sub` 매핑 = **235키 중 234 clean 1:1**, l7 없는 키 0, 모호(>1 l7) 1키.
- mapper 빈 l7_sub = 115행 / ~23 distinct 키. 그중 **21키는 master JOIN 으로 backfill 가능**, ~4키만 잔존(주로 `wa` 빈 값 또는 master에 그 wa 조합 부재).
- 철콘 FAB 실 구조: 거푸집공사 l7.5 3종 / 철근공사 9 / 콘크리트공사 29 / PSRC공사 6 / 빈값 8(대부분 master로 복구) = 47.

## 3. 결정

- **접근법 A — BE에서 l7 도출 + master backfill.** registered route가 l7.5 카드마다 `l7_label = COALESCE(MAX(mapper.l7_sub), master JOIN, '기타')` 를 계산해 카드에 실어 내리고, FE는 `l7_label` 로 그룹핑.
- **적용 범위 = 등록(누적) 모드 우측 카드만.** 좌측 WBS 트리 불변, HIL(검토대기) 모드 불변.
- **디자인 불가침 준수:** `WpGroup` 컴포넌트의 markup·스타일 변경 없음. 그린 헤더에 들어가는 라벨(l7)과 그룹 분할만 데이터로 바뀐다.

대안 기각: B(mapper.l7_sub만, master backfill 없음) = 빈 23키가 전부 "기타"로 새어 거푸집/철근 일부 누락 → 부정확. C(master JOIN 권위만) = mapper 99.8% 보유분 미사용 + 모호 1키 tie-break 과함.

## 4. 설계

### 4.1 데이터 계약
- `web/lib/types.ts` `ReviewItem` 에 `l7_label?: string` 추가 (optional — HIL 카드는 미설정).
- `web/app/api/mock/review/registered/route.ts` 쿼리 변경:

```sql
WITH master_l7 AS (
  SELECT wa, l6_main, l7_5_activity, MAX(NULLIF(l7_sub,'')) AS m_l7
  FROM activity_master WHERE site_id = ${siteId}
  GROUP BY wa, l6_main, l7_5_activity
)
SELECT ma.wa, ma.l6_main,
       COALESCE(NULLIF(ma.l7_5_activity,''),'미분류') AS l75_label,
       COALESCE(MAX(NULLIF(ma.l7_sub,'')), MAX(ml.m_l7), '기타') AS l7_label,
       ROUND(SUM(ma.today_qty)::numeric,2) AS cum_qty,
       MAX(ma.unit) AS unit, MAX(ma.company) AS company,
       COUNT(DISTINCT ma.company) AS company_n
FROM mapper_activities ma JOIN pipeline_runs pr USING (run_id)
LEFT JOIN master_l7 ml
  ON ml.wa = ma.wa AND ml.l6_main = ma.l6_main AND ml.l7_5_activity = ma.l7_5_activity
WHERE pr.site_id = ${siteId} AND ma.is_mock = ${useMock}
  AND ma.l6_main IS NOT NULL AND ma.trade IN ('건축','토목') AND ma.requires_review = FALSE
  AND (${waParam}::text IS NULL OR ma.wa = ${waParam})
  AND (${l6}::text IS NULL OR ma.l6_main = ${l6})
  AND (${l5}::text IS NULL OR ma.l5_disc = ${l5})
GROUP BY ma.wa, ma.l6_main, l75_label
ORDER BY cum_qty DESC
```

- `master_l7` 는 (wa,l6,l7.5)당 1행이라 LEFT JOIN 팬아웃 없음. 모호 1키는 `MAX` 로 결정론적 수렴.
- 매핑 우선순위: 그룹 내 `MAX(mapper.l7_sub)`(부분 빈값 자동 보정) → master → `기타`.
- `route.ts` item 매핑에 `l7_label: r.l7_label` 추가.

### 4.2 그룹핑
- `web/lib/review-group.ts` 에 `groupCardsByL7(cards: ReviewItem[]): WpGroup[]` 신규:
  - **그룹 키 = `wpId = `${ai_mapped_wp_id}::${l7_label}``** (= `wa-l6::l7`). `l7_label` 없으면 `기타`.
    - 이 합성 키가 (a) **React `key` / `data-wp-group` 고유성** 보장 (`page.tsx:270`, `WpGroup.tsx:29` — 같은 (wa,l6) 아래 거푸집/철근/콘크리트 4그룹이 동일 wpId 공유 시 key 충돌 발생 → 반드시 합성), (b) l7 그룹을 **(wa,l6) 스코프 안에 한정**(building 노드 선택 시 wa/l6 필터 없이 전체 조회되어 같은 l7명 "콘크리트공사"가 CUB·FAB 동시 등장 → 전역 l7 키면 오병합. `wa-l6` 포함으로 분리).
  - `WpGroup.wpName = l7_label`, `WpGroup.path = splitPath(raw[0].ai_mapped_path).path`(site>wa>l6).
  - 정렬: 그룹 = Σ`item.quantity`(= route `cum_qty`, `registered/route.ts:51`) DESC, **동률 시 `wpName.localeCompare` tie-break**(결정론 — 기존 `groupCardsByWp` 와 동일 패턴, vitest 안정). 그룹 내 카드 = `quantity` DESC.
  - `items`/`confirmedCount`/`unconfirmedCount`/`allConfirmed` 등 `WpGroup` 형태 그대로 (registered 는 전부 `confirmed`).
  - 구현 주석: `WpGroup.wpId` JSDoc(`review-group.ts:4`, "ai_mapped_wp_id = 연결선 타깃")이 `groupCardsByL7` 경로에선 `wa-l6::l7` 합성임을, "연결선 타깃은 카드의 `ai_mapped_wp_id`(별개)"임을 한 줄 보강.
- 기존 `groupCardsByWp` **불변** (HIL 전용).

### 4.3 화면
- `web/app/(app)/review/page.tsx:93` 분기:
  `const groups = useMemo(() => onlyUnconfirmed ? groupCardsByWp(cards) : groupCardsByL7(registered), [...])`.
- `WpGroup` 렌더링·props·스타일 불변. 그린 헤더 텍스트가 l7(예: "거푸집공사")로 표시될 뿐.

### 4.4 엣지케이스
- 그룹 내 일부 행만 빈 l7_sub → `MAX(NULLIF())` 가 비지 않은 값 채택.
- 키 전체가 빈 l7_sub → master backfill → 그래도 없으면 `기타` 그룹.
- l7.5 자체가 빈 값 → 카드 `미분류`, l7 은 `기타`.
- registered 0건 / 노드 미선택 → 기존 빈 상태 메시지 유지.

## 5. 변경 파일
- `web/lib/types.ts` — `ReviewItem.l7_label?: string`
- `web/app/api/mock/review/registered/route.ts` — 쿼리 + item 매핑
- `web/lib/review-group.ts` — `groupCardsByL7` 추가
- `web/app/(app)/review/page.tsx` — registered 모드 그룹핑 분기

## 6. 검증
- 단위(vitest): **신규 파일** `web/lib/__tests__/review-group.test.ts` (현재 `__tests__/` 엔 `transforms.test.ts` 만 존재) 에 `groupCardsByL7` 케이스 — l7_label 로 묶임, 빈 l7_label→기타, **같은 (wa,l6) 내 복수 l7 → wpId 고유**, 같은 l7명이 서로 다른 (wa,l6)에 → 분리 유지, 정렬.
- route 테스트: l7_label COALESCE 우선순위(mapper>master>기타) — 가능하면 fixture/모킹.
- 실 API(npm dev :5537): 철콘 FAB 선택 시 **거푸집공사(3)/철근공사(9)/콘크리트공사(29)/PSRC공사(6) = 47** 4그룹으로 분리(현재 한 통 47). 토목 토공사 선택 시 터파기 및 되메우기 / 시험터파기 등 l7 그룹 확인.

## 7. 범위 밖
- 좌측 WBS 트리에 l7 레벨 추가 (현행 site>wa>l5>l6 유지).
- HIL 검토대기 모드 l7 그룹핑 (후속 필요 시 `/api/mock/review` 에 l7_label 추가).
- 좌측 카드 숫자 grain 변경 (l7.5 현황유지 — 별도 결정).
- 보드(ReactFlow) 뷰 l7 그룹핑.

## 8. 리스크
- 병행 세션이 같은 브랜치(`feature/review-l75-hil`)에서 작업 중 — 변경 파일(types/route/review-group/page) 충돌 주의, 머지 전 rebase 확인.
- `master_l7` JOIN 으로 registered 쿼리 비용 소폭 증가 (site당 235행 CTE, 무시 가능).
