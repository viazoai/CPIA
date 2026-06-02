# Human Review 보드 뷰 — WBS·작업물량 노드-링크 마인드맵 (React Flow)

> **트랙:** B_Track (`web/`)
> **대상 화면:** `/review` — 기존 리스트 뷰에 **탭으로 추가되는 두 번째 뷰**
> **목표:** WBS 위계(프로젝트›건물›공종›WP)와 작업물량을 n8n/마인드맵식 **노드-링크 캔버스**로 시각화. 검토 대상 작업물량만 강조하고, 작업물량을 다른 WBS 노드로 드래그해 재연결(remap)·확정할 수 있게 한다.

---

## 배경

기존 `/review` 리스트 뷰(2026-06-02 spec, WP 그룹핑+연결선)는 **그대로 유지**한다. 사용자는 이와 별개로, "사람이 검토할 항목만 한눈에 보이고, 좌측 WBS 구조 위에 작업물량을 시각적으로 얹어 다른 노드로 재배치할 수 있는" 뷰를 원했다. 핵심 멘탈모델은 **마인드맵 / n8n 노드 그래프**: 좌→우로 위계가 가지치고, 말단 WP에서 작업물량으로 연결선이 뻗는다.

---

## 채택 결정 (브레인스토밍 확정)

| 항목 | 결정 |
|------|------|
| 위치 | `/review` 상단 탭 토글 (`리스트` / `보드`). 같은 페이지, 데이터·핸들러 공유 |
| 레이아웃 | 좌→우 마인드맵: **프로젝트 › 건물 › 공종 › WP › 작업물량** 5열 노드-링크 |
| 렌더링 | **React Flow (`@xyflow/react`)** — 노드·bezier 엣지·드래그·팬/줌 기본 제공 |
| 노드 색 | WBS 위계 4단계(프로젝트·건물·공종·WP) **전부 흰색**; 작업물량은 흰색, **검토 대상만 sun 강조** |
| 접기/펼치기 | 위계 노드 클릭 → 하위 가지 토글 (collapsed Set) |
| 필터 | "검토만" 토글은 **작업물량 노드에만** 작용. **WBS 위계 노드는 항상 전부 표시** (검토 자식이 없어도 — remap 드롭 타깃이므로 절대 숨기지 않음) |
| 액션 | **리맵**(작업물량 노드를 다른 WBS 노드로 드래그) + **확정**(노드/툴바). `/api/hil/resume` 재사용 |

---

## 데이터 (기존 재사용, 변경 없음)

- 소스: 리스트 뷰와 동일 — `/api/mock/review` → `{ wbs: WBSNode, cards: ReviewItem[] }`, 등록 모드는 `/api/mock/review/registered`.
- `WBSNode`: `id, type("building"|"trade"|"work_package"), name, parent_id, review_count, total_count, status, children?, wa?, l6_main?`. 트리 깊이: building(0) → trade=WA(1) → trade=l5_disc(2) → work_package(3). (프로젝트 루트는 building 노드를 "프로젝트"로 표기; 실제 트리 최상위가 곧 프로젝트/현장)
- `ReviewItem`: `id, idx, bp_name, work_content, quantity, unit, ai_mapped_wp_id, ai_mapped_path, wa, l6_main, confidence, status, remapped?, alternative_wps?`. 각 작업물량은 `ai_mapped_wp_id`(= WP 노드 id)에 연결.
- 검토 대상 판정: 리스트 뷰와 동일 — `status === "unconfirmed"` (HIL 모드 기준).

> 보드는 별도 API를 만들지 않는다. 이미 가진 `wbs` 트리 + `cards` 로 그래프를 구성한다.

---

## 컴포넌트 설계

### 1. `/review` 페이지 — 뷰 토글

- `page.tsx` 에 `view: "list" | "board"` 상태 + 헤더 우측 탭(세그먼트) UI 추가. 기본 `"list"`.
- `view === "list"` → 기존 그리드(WBSTree + 그룹 리스트 + 연결선) **그대로**.
- `view === "board"` → `<ReviewBoard wbs={wbs} cards={현재 모드 리스트} onConfirm onRemap onConfirmAll ... />`.
- `wbs`·`cards`·`registered`·`onlyUnconfirmed`·핸들러는 이미 페이지에 있으므로 그대로 전달. 보드는 그 props 만 받는 순수 표현 컴포넌트(자체 fetch 없음).

### 2. `ReviewBoard.tsx` (신규, React Flow)

- `@xyflow/react` 의 `<ReactFlow>` 캔버스. `nodes`/`edges` 는 `useMemo` 로 `wbs`+`cards`+`collapsed`+`reviewOnly` 에서 파생.
- **노드 타입 2종 (커스텀)**:
  - `HierNode` — 프로젝트/건물/공종/WP 공통. 흰색 카드, 좌측 `▾/▸` 캐럿(자식 있을 때), 라벨 + 집계 배지(예: 미확정 수). 클릭 → collapse 토글.
  - `QtyNode` — 작업물량. 흰색; `status==="unconfirmed"` 이면 sun 강조(`bg-sun`/`border-sun-deep`). bp_name + work_content + confidence%. 확정 버튼(작은) + 드래그로 remap.
- **엣지**: React Flow `type:"default"`(bezier). 검토 작업물량으로 가는 엣지는 sun 색·굵게, 나머지 회색.
- **레이아웃 (`lib/board-layout.ts`, 신규 순수 함수)**: 좌→우 트리 배치.
  - x = 노드 깊이 × 열 간격(작업물량은 WP 다음 열). 깊이: 루트=0 … WP=3, 작업물량=4.
  - y = 리프(보이는 작업물량 + 자식 없는 위계 노드) 순서대로 누적; 부모 노드 y = 자식 y 들의 평균(가운데 정렬).
  - `collapsed`·`reviewOnly` 반영해 "보이는" 노드만 배치.
  - 출력: `{ id → {x,y} }` (React Flow `position`).
- **데이터 → 그래프 빌드 (`lib/board-graph.ts`, 신규 순수 함수)**:
  - `buildBoardGraph(wbs, cards, { collapsed, reviewOnly })` → `{ nodes, edges }`.
  - 위계 노드: WBS 트리 전부(필터 무관 — 항상 포함). collapsed 노드의 하위는 제외.
  - 작업물량 노드: `cards` 를 `ai_mapped_wp_id` 로 각 WP 에 매단다. `reviewOnly` 면 `status==="unconfirmed"` 만. **WP·상위 위계는 작업물량이 0이어도 유지**.
  - 엣지: 위계 부모-자식 + WP→작업물량. (collapsed/숨김 노드로 가는 엣지는 제외)

### 3. 인터랙션

- **접기/펼치기**: `HierNode` 클릭 → `collapsed` Set 토글 → nodes/edges/layout 재계산. (작업물량 노드 클릭은 선택/확정용, collapse 아님)
- **필터**: 캔버스 상단 "검토만" 토글 → `reviewOnly`. 작업물량 노드만 축소, WBS 위계는 불변.
- **리맵(드래그)**: 작업물량 노드를 드래그 → `onNodeDragStop` 에서 드롭 위치가 어떤 WP(`HierNode` type=work_package) 위인지 히트테스트 → 맞으면 `onRemap(cardId, wpId, path)` (기존 핸들러 재사용), 엣지가 새 WP 로 재연결. 드롭이 WP 밖이면 원위치 복귀.
  - 정밀 지정 보조: 노드의 "수정" → 기존 `WPSearchCombobox` 재사용(선택).
- **확정**: `QtyNode` 의 확정 버튼 → `onConfirm(cardId)`. 캔버스 툴바에 「확신도 0.8↑ 일괄확정」 + 「모두 확정」 → 기존 `handleConfirmHighConf`/`handleConfirmAll`. 미확정 0 시 `/api/hil/resume`.
- 팬/줌/미니맵: React Flow 기본(`<Controls/>`, 선택적 `<MiniMap/>`).

---

## 상태 & 데이터 흐름

```
page.tsx (기존)  ── view="board" ──▶ <ReviewBoard wbs cards onConfirm onRemap onConfirmAll />
ReviewBoard:
   collapsed:Set, reviewOnly:bool  (보드 로컬 상태)
   buildBoardGraph(wbs, cards, {collapsed, reviewOnly}) ─▶ {nodes, edges}
   boardLayout(nodes/edges 위계)                          ─▶ position 주입
   HierNode 클릭 ─▶ collapsed 토글
   "검토만" 토글 ─▶ reviewOnly
   QtyNode 드래그 → WP 드롭 ─▶ onRemap(=page.handleRemap)
   QtyNode 확정 / 툴바 ─▶ onConfirm / handleConfirmHighConf / handleConfirmAll ─▶ (미확정 0) /api/hil/resume
```

---

## 의존성

- **신규**: `@xyflow/react` (React Flow v12). `web/package.json` 에 추가 + `npm install`. CSS `@xyflow/react/dist/style.css` 임포트.
- 기존 React 18 / Next 14 / Tailwind 호환 확인(React Flow v12는 React 18 지원).

## 영향 파일 (예상)

- `web/app/(app)/review/page.tsx` — `view` 토글 + 탭 UI + 보드 분기 렌더 (리스트 경로 불변).
- 신규 `web/app/components/review/ReviewBoard.tsx` — React Flow 캔버스 + 커스텀 노드/엣지/툴바.
- 신규 `web/app/components/review/board/HierNode.tsx`, `QtyNode.tsx` — 커스텀 노드.
- 신규 `web/lib/board-graph.ts` — `buildBoardGraph` (순수, 테스트 대상).
- 신규 `web/lib/board-layout.ts` — 좌→우 트리 좌표 계산 (순수, 테스트 대상).
- `web/package.json` — `@xyflow/react` 의존성.

## 비목표 (YAGNI)

- 자동 레이아웃 라이브러리(dagre/elk) — 커스텀 트리 배치로 충분.
- 보드에서 신규 작업일보 업로드·파이프라인 트리거 등 검토 외 기능.
- 등록(열람) 모드의 보드 read-only 정교화는 후순위 — 우선 HIL 검토 모드 중심. (등록 모드에서도 보드를 열 수 있으나 작업물량은 readOnly 표시)
- 실데이터 연결 변경(API는 기존 그대로).

## 검증

- 순수 로직(`buildBoardGraph`·`board-layout`)은 vitest TDD: 위계 포함/필터/collapsed 반영, 작업물량 매달기, 좌표 단조성·부모 가운데 정렬.
- 컴포넌트: `HierNode` collapse 토글, `QtyNode` 검토 강조·확정 콜백 (testing-library; React Flow 캔버스 전체 렌더는 jsdom 한계로 노드 컴포넌트 단위 테스트 중심).
- 타입·빌드: `npx tsc --noEmit` src-level 0 에러(로컬 `next build` 는 `.next` 권한으로 불가 — dev 컨테이너 HMR + tsc 로 검증). Set/Map downlevel-iteration 회피(tsconfig `target` 미지정).
- 수동: dev 컨테이너(5537) `/review` 보드 탭 — 마인드맵 렌더, 검토 강조, 접기/펼치기, 검토만 필터(WBS 유지), 드래그 리맵→엣지 재연결, 확정/일괄→resume.
