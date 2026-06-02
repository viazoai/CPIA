# Human Review — WBS ↔ 작업물량 연결 표현 재설계 (C · 하이브리드)

> **트랙:** B_Track (`web/`)
> **대상 화면:** `/review` — H-i-L 1 (Mapper 이후 사람 검토)
> **목표:** AI가 매핑한 "작업물량 → WBS Work Package" 연결을 사람이 빠르게 검토·수정할 수 있도록, **1:N 집계**와 **연결 관계**를 한 화면에서 직관적으로 드러낸다.

---

## 문제 정의

현재 `/review` 화면은 좌측 WBS 트리(`md:col-span-4`) + 우측 작업물량(`md:col-span-8`)의 2분할 구조다. `onlyUnconfirmed` 토글이 단순 필터가 아니라 **모드 스위치**로 동작한다:

- **HIL 검토 모드**(`onlyUnconfirmed=true`): 신규 미확정 `cards`를 검토·확정·수정. 트리 노드 선택 시 해당 WP 하위로 카드를 필터. footer에 "모두 확정" 버튼.
- **등록 열람 모드**(`onlyUnconfirmed=false`): 선택 노드 스코프의 누적 등록 작업을 서버에서 lazy fetch(`/api/mock/review/registered`), `ReviewCard`는 `readOnly`. `handleConfirmAll` 후 이 모드로 자동 복귀하며 `confirmedNotice` 표시.

검토자가 호소한 두 가지 통증(두 모드 공통):

1. **1:N 집계가 안 보임** — 한 WP에 여러 작업물량이 묶이는 관계가 드러나지 않고 개별 카드만 평면 나열된다.
2. **좌↔우 시선 이동** — 카드는 매핑 경로를 텍스트(`ai_mapped_path`)로만 보여줘서, 그게 좌측 트리의 어느 노드인지 시선을 옮겨 대조해야 한다.

규모는 작은~중간(작업물량 ~10–20건, WP ~5–10개/현장·일).

---

## 채택안: C · 하이브리드 (그룹핑 + 포커스 연결선) — 두 모드 모두 적용

검토한 3안 중 선택:

- **A · WP 그룹 아코디언** — 집계는 풀지만 그래픽 연결 느낌이 약함.
- **B · 양분 노드-링크** — 그래픽은 강하나 20건+에서 엣지가 빽빽해지고 시선 이동이 남음.
- **C · 하이브리드 (채택)** — 우측을 WP로 그룹핑해 집계를 상시 노출하고, 카드↔트리 노드 연결선으로 시선을 안내.

**모드별 적용 범위:**

| 요소 | HIL 검토 모드 | 등록 열람 모드 |
|------|--------------|---------------|
| WP 그룹핑(집계 헤더) | ✅ | ✅ |
| 연결선(카드↔트리 노드) | ✅ | ✅ (read-only) |
| 확정 항목 접힘 요약 | ✅ | — (전 항목 등록 상태) |
| footer 일괄 확정 2버튼 | ✅ | — |
| 드래그&드롭 리맵 / 수정 | ✅ | — (readOnly) |
| 트리 노드 클릭 동작 | 그룹 스크롤+하이라이트 | 노드 스코프 fetch(현행 유지) |

---

## 데이터 모델 (기존, 변경 없음)

- 각 **작업물량 항목**(`ReviewItem`)은 정확히 하나의 WBS Work Package(`ai_mapped_wp_id`)에 연결 — 다대일.
- 카드 필드: `ai_mapped_wp_id`, `ai_mapped_path`, `confidence`, `alternative_wps[]`, `work_content`, `bp_name`, `quantity`, `unit`, `wa`, `l6_main`, `status`('unconfirmed'|'confirmed'), `remapped`, `idx`.
- WBS 트리(`WBSNode`): 건물 › 공종 › Work Package, 노드별 `total_count`·`review_count`.
- 데이터 소스: HIL `cards` ← `/api/mock/review`; 등록 `registered` ← `/api/mock/review/registered?wa=&l5=&l6=` (노드 스코프, `nodeToQuery`로 파라미터 생성). resume ← `/api/hil/resume`. 모두 현행 유지.

---

## 컴포넌트 설계

### 1. 레이아웃 & 연결선 오버레이

- grid 유지: 좌 WBS 트리 `md:col-span-4` + 우 작업물량 `md:col-span-8` (현행 너비 유지 — 너비 변경은 본 작업의 목표 아님).
- **연결선 SVG 오버레이**: 우측 `<section>`의 grid 영역 전체를 덮는 `position:absolute; inset:0; pointer-events:none` 레이어. 두 칼럼 경계를 가로질러야 하므로 한쪽 패널 내부가 아닌 grid 컨테이너 위에 둔다. 카드·트리 클릭은 `pointer-events:none`으로 통과.
- 좌표 계산: 선택 카드의 좌측 가장자리 중앙(앵커)과 대상 트리 노드의 우측 가장자리 중앙(앵커)을 각각 `getBoundingClientRect()` 기준 grid-relative 좌표로 변환, 베지어 곡선(`<path d="M..C..">`)으로 연결.
- 색: 확신도 티어 — 저확신(< 0.8) 주황(`--sun`), 고확신/등록 민트(`--mint`).
- 재드로잉: 우측 패널 스크롤, 트리 스크롤, 윈도우 리사이즈 시 좌표 재계산 (스크롤 이벤트 + `ResizeObserver`).

### 2. 우측 패널 — WP 그룹핑 (집계 상시, 두 모드 공통)

- 현재 모드의 항목(HIL=`cards` 미확정/확정, 등록=`registered`)을 `ai_mapped_wp_id` 기준으로 그룹화. 그룹 = WP 하나.
- **그룹 헤더**: WP 이름(말단) + 경로(상위 건물›공종, 옅게) + 집계 배지 + 그룹 확신도.
  - HIL: `확정 N · 미확정 M` + 그룹 내 **미확정 항목의 최저 확신도**(미확정 없으면 생략). 미확정 포함 그룹 주황 톤, 전부 확정 민트 톤.
  - 등록: `등록 N건` (확신도/미확정 개념 없음, 민트 톤).
- **정렬**: HIL — ① 미확정 포함 그룹을 위로(그 안에서 최저 확신도 오름차순), ② 전부 확정 그룹은 하단 얇은 1줄 바로 접음. 등록 — WP 경로 순(또는 건수 순).
- **확정 항목 처리 (HIL only, 안 A)**: 그룹 내 미확정만 풀 카드, 확정 항목은 `✓ 확정 N건 — 펼치기 ▾` 한 줄 요약으로 접음. (등록 모드는 전 항목이 read-only 카드 → 접힘 없음)
- **카드 행 버튼(HIL only)**: `확정`·`수정` 버튼을 행 **오른쪽 끝** 정렬. (`ReviewCard`의 `readOnly`면 버튼 미노출 — 현행 prop 활용)

### 3. 연결선 트리거 & 양방향 시선 연결

- **카드 클릭(선택)** → ① 연결선 고정, ② 대상 WP 트리 노드 선택 상태, ③ 노드가 접혀있거나 스크롤 밖이면 **조상 자동 펼침 + 트리 스크롤**로 노드를 화면에 들인 뒤 연결선 그림. (HIL·등록 공통)
- **트리 노드 클릭** (모드별):
  - HIL: 기존의 wpIds 필터(89–100행)를 **폐지**하고, 우측 해당 WP 그룹으로 스크롤+하이라이트. 필터링은 `onlyUnconfirmed` 토글이 전담.
  - 등록: **현행 유지** — 노드 스코프 `registered` lazy fetch 트리거(`nodeToQuery`).
- 선택 상태: 기존 `selectedNodeId`에 더해 `selectedCardId` 신설. 카드 선택 시 동기화.

### 4. 리맵 (매핑 변경, HIL only)

- **메인 제스처 — 카드 드래그&드롭**: 카드를 좌측 트리의 WP 노드로 끌어 놓으면 리맵(`onDrop` → `handleRemap`, 기존 로직 재사용). 드롭 대상 노드 강조 보강. **드롭 완료 시 연결선이 새 노드로 이어지는** 전환 애니메이션으로 "연결됨"을 표현.
- **정밀 보조 — 검색 콤보박스**: 카드의 `수정` 버튼 → `WPSearchCombobox`로 WP 정밀 지정 (기존 유지).
- (와이어 끝점 rewire 방식은 채택하지 않음. 등록 모드는 readOnly라 리맵 불가.)

### 5. 하단 일괄 액션 (footer, HIL only)

- **「확신도 0.8↑ 일괄 확정」**: 미확정 중 `confidence ≥ 0.8` 항목만 AI 추천대로 일괄 확정. 저확신 항목은 남겨 사람이 검토. 미확정이 남으므로 모드 전환·resume 보류. (신규 핸들러)
- **「모두 확정」**: 남은 미확정 전부를 AI 추천대로 확정 → 현행 `handleConfirmAll` 흐름(미확정 0 → 등록 모드 자동 복귀 + `confirmedNotice` + `/api/hil/resume`) 유지.
- corrections 전송: 사용자가 remap한 카드(`remapped && wa && l6_main`)만 `corrections[idx] = { wa, l6_main }`로 함께 전송 (현행 유지).
- 임계값 0.8 고정 (추후 조절형 확장 여지).

---

## 상태 & 데이터 흐름

```
[HIL 모드]  /api/mock/review → cards
   cards(미확정+확정) ──group by ai_mapped_wp_id──▶ 그룹 리스트(미확정 우선)
   selectedCardId ──▶ 연결선(card anchor ↔ tree node anchor) + 트리 자동 펼침·스크롤
   selectedNodeId(트리클릭) ──▶ 우측 그룹 스크롤+하이라이트 (필터 폐지)
   드래그&드롭 / 검색 콤보박스 ──▶ handleRemap(confidence=1.0, remapped=true)
   0.8↑ 일괄 / 모두 확정 ──▶ status='confirmed'
   미확정 == 0 (모두 확정) ──▶ onlyUnconfirmed=false + confirmedNotice + POST /api/hil/resume

[등록 모드]  selectedNodeId ──nodeToQuery──▶ /api/mock/review/registered → registered(read-only)
   registered ──group by ai_mapped_wp_id──▶ 그룹 리스트
   selectedCardId ──▶ 연결선 (read-only)
```

---

## 보존(변경 없음)

- 데이터 소스 `/api/mock/review`, `/api/mock/review/registered`, resume `/api/hil/resume`.
- `onlyUnconfirmed` 모드 스위치, `handleConfirm`/`handleRemap`/`handleConfirmAll`의 핵심 상태 전이, `confirmedNotice`·`registered`·`registeredTotal`·`registeredError` 로직, `nodeToQuery`.
- `WBSTree` 드롭 타깃(`onDrop`), `WPSearchCombobox`, `ReviewCard`의 `readOnly` prop.

## 영향 파일 (예상)

- `web/app/(app)/review/page.tsx` — 그룹핑·연결선 오버레이·`selectedCardId` 상태·HIL footer 두 버튼·트리클릭 필터→스크롤 전환.
- `web/app/components/review/WBSTree.tsx` — 노드 자동 펼침/스크롤 API, 노드 앵커 ref 노출, 트리클릭 모드별 연동.
- `web/app/components/review/ReviewCard.tsx` — 버튼 우측 정렬, 선택/확정-접힘 상태, 카드 앵커 ref (readOnly 분기 유지).
- 신규: 연결선 오버레이 컴포넌트(예: `ReviewConnector.tsx`), WP 그룹 헤더/접힘 요약 컴포넌트.

## 비목표 (YAGNI)

- 양분 노드-링크 전체 그래프(B안), 와이어 끝점 rewire(A안).
- 임계값 슬라이더(0.8 고정), 너비 변경.
- 실데이터 연결(`/api/mock/review*` → 실 파이프라인) — 별도 후속.
- 다중 카드 선택/일괄 remap.

## 검증

- 시연 시나리오(0925)로 수동 확인: 그룹핑·집계 배지, 카드 클릭→연결선+트리 자동 펼침, 드래그 리맵→연결선 전환, 0.8↑/모두 확정→모드 복귀·resume, 등록 모드 그룹핑·연결선(read-only), 모드 토글.
- `npm run build` 타입·빌드 통과.
- 5536/5537(HMR)에서 인터랙션 확인 후 시연 직전 5535 재빌드.
