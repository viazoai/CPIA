# CPIA review 우측 작업물량 카드 l7 그룹핑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** review 페이지 우측 "작업물량" 등록(누적) 카드를 l7.5 평면 나열에서 l7(l7_sub) 기준 그룹으로 묶어 보여준다.

**Architecture:** registered route(BE)가 l7.5 카드마다 l7 라벨을 `COALESCE(MAX(mapper.l7_sub), master_l7 JOIN, '기타')` 로 도출해 카드에 실어 내리고, FE는 신규 순수함수 `groupCardsByL7` 로 묶는다. 그룹 `wpId = ai_mapped_wp_id::l7_label` 합성으로 React key 충돌·(wa,l6) 오병합을 막는다. 좌측 트리·HIL 모드·`WpGroup` markup 은 불변.

**Tech Stack:** Next.js(App Router) + TypeScript, postgres.js(`@/lib/pg` tagged template), vitest(jsdom), PostgreSQL(`activity_master`/`mapper_activities`).

**Spec:** `docs/superpowers/specs/2026-06-04-cpia-review-l7-grouping-design.md`

**전제 (실측 확인됨):**
- dev 서버 npm dev `:5537`, FastAPI `:8000` 가동 중. DB `postgresql://cpia:***@43.200.85.209:5532/cpia`.
- 검증 site = `m15x-ph3-ibl`. 철콘 FAB 정답: 거푸집공사(3)/철근공사(9)/콘크리트공사(29)/PSRC 공사(6) = 47.
- `mapper_activities.l7_sub` 99.8% 채워짐, master `(wa,l6,l7.5)→l7_sub` 235키 중 234 clean 1:1.
- 브랜치 `feature/review-l75-hil` (병행 세션 활성 — 변경 4파일만 stage 후 커밋).

**파일 구조 (변경 4파일):**
- `web/lib/types.ts` — `ReviewItem.l7_label?: string` 추가 (데이터 계약)
- `web/lib/review-group.ts` — `groupCardsByL7` 신규 (순수 그룹핑). 기존 `groupCardsByWp` 불변
- `web/app/api/mock/review/registered/route.ts` — 쿼리에 master_l7 JOIN + l7_label, item 매핑
- `web/app/(app)/review/page.tsx` — 등록 모드 그룹핑 분기

---

### Task 1: `groupCardsByL7` 순수 함수 (TDD)

**Files:**
- Modify: `web/lib/types.ts:139-154` (`ReviewItem` 에 `l7_label?` 추가)
- Modify: `web/lib/review-group.ts` (`groupCardsByL7` 추가)
- Test: `web/lib/__tests__/review-group.test.ts` (신규)

- [ ] **Step 1: `ReviewItem` 에 `l7_label?` 추가**

`web/lib/types.ts` `ReviewItem` 의 `alternative_wps?` 아래에 추가:

```ts
  alternative_wps?: { id: string; path: string; score: number }[];
  l7_label?: string;            // l7(l7_sub) 그룹 라벨 — registered 카드 전용(groupCardsByL7). HIL 카드는 미설정.
}
```

- [ ] **Step 2: 실패 테스트 작성**

`web/lib/__tests__/review-group.test.ts` (신규):

```ts
import { describe, it, expect } from "vitest";
import { groupCardsByL7 } from "../review-group";
import type { ReviewItem } from "../types";

// 테스트용 ReviewItem 팩토리 — 필수 필드만 채우고 나머지 기본값.
function mk(p: Partial<ReviewItem>): ReviewItem {
  return {
    id: p.id ?? Math.random().toString(36).slice(2),
    idx: -1,
    bp_name: p.bp_name ?? "남웅건설",
    work_content: p.work_content ?? "타설",
    quantity: p.quantity ?? 0,
    unit: p.unit ?? "m3",
    ai_mapped_wp_id: p.ai_mapped_wp_id ?? "fab-철근콘크리트공사",
    ai_mapped_path: p.ai_mapped_path ?? "M15X > FAB > 철근콘크리트공사 > 타설",
    wa: p.wa ?? "FAB",
    l6_main: p.l6_main ?? "철근콘크리트공사",
    confidence: p.confidence ?? 1.0,
    status: p.status ?? "confirmed",
    l7_label: p.l7_label,
    alternative_wps: [],
  };
}

describe("groupCardsByL7", () => {
  it("l7_label 로 묶고 그룹명=l7, 같은 (wa,l6) 내 복수 l7 분리", () => {
    const cards = [
      mk({ l7_label: "거푸집공사", quantity: 100, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > 기초공사 : 거푸집 공사" }),
      mk({ l7_label: "거푸집공사", quantity: 50, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > RC : 거푸집 공사" }),
      mk({ l7_label: "철근공사", quantity: 80, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > 기초공사 : 철근 조립" }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups.map((g) => g.wpName)).toEqual(["거푸집공사", "철근공사"]); // Σqty: 거푸집150 > 철근80
    expect(groups[0].items).toHaveLength(2);
    expect(groups[0].path).toBe("M15X > FAB > 철근콘크리트공사");
    // wpId 고유 (key 충돌 방지)
    expect(new Set(groups.map((g) => g.wpId)).size).toBe(2);
  });

  it("빈/누락 l7_label → '기타' 그룹", () => {
    const cards = [
      mk({ l7_label: undefined, quantity: 10 }),
      mk({ l7_label: "", quantity: 5 }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups).toHaveLength(1);
    expect(groups[0].wpName).toBe("기타");
  });

  it("같은 l7명이 서로 다른 (wa,l6) → 별도 그룹 (오병합 방지)", () => {
    const cards = [
      mk({ l7_label: "콘크리트공사", ai_mapped_wp_id: "fab-철근콘크리트공사", wa: "FAB", quantity: 100 }),
      mk({ l7_label: "콘크리트공사", ai_mapped_wp_id: "cub-철근콘크리트공사", wa: "CUB", quantity: 30 }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups).toHaveLength(2);
    expect(new Set(groups.map((g) => g.wpId)).size).toBe(2);
  });

  it("그룹 내 카드 quantity DESC 정렬", () => {
    const cards = [
      mk({ l7_label: "콘크리트공사", quantity: 5, work_content: "작음" }),
      mk({ l7_label: "콘크리트공사", quantity: 99, work_content: "큼" }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups[0].items.map((c) => c.work_content)).toEqual(["큼", "작음"]);
  });
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd web && npx vitest run lib/__tests__/review-group.test.ts`
Expected: FAIL — `groupCardsByL7 is not a function` (또는 import 에러).

- [ ] **Step 4: `groupCardsByL7` 구현**

`web/lib/review-group.ts` 파일 끝에 추가 (기존 `splitPath`, `WpGroup`, `groupCardsByWp` 재사용/불변):

```ts
// 등록(누적) 카드 전용 — l7(l7_sub) 라벨로 묶는다. wpId 는 (wa,l6) 스코프를 포함한 합성키.
// (key 충돌·동명 l7 오병합 방지. 연결선 타깃은 카드의 ai_mapped_wp_id 별개로 유지.)
export function groupCardsByL7(cards: ReviewItem[]): WpGroup[] {
  const l7Of = (c: ReviewItem) => (c.l7_label && c.l7_label.trim() ? c.l7_label : "기타");
  const byKey = new Map<string, ReviewItem[]>();
  for (const c of cards) {
    const wpId = `${c.ai_mapped_wp_id}::${l7Of(c)}`;
    const arr = byKey.get(wpId) ?? [];
    arr.push(c);
    byKey.set(wpId, arr);
  }

  const groups: WpGroup[] = [];
  byKey.forEach((raw, wpId) => {
    const items = [...raw].sort((a, b) => b.quantity - a.quantity);
    const unconfirmed = items.filter((c) => c.status === "unconfirmed");
    const confirmed = items.filter((c) => c.status === "confirmed");
    const { path } = splitPath(raw[0].ai_mapped_path);
    groups.push({
      wpId,
      wpName: l7Of(raw[0]),
      path,
      items,
      confirmedCount: confirmed.length,
      unconfirmedCount: unconfirmed.length,
      minUnconfirmedConfidence: unconfirmed.length
        ? Math.min(...unconfirmed.map((c) => c.confidence))
        : null,
      allConfirmed: unconfirmed.length === 0,
    });
  });

  // 그룹 정렬: Σquantity DESC, 동률 wpName localeCompare(결정론).
  return groups.sort((a, b) => {
    const sa = a.items.reduce((s, c) => s + c.quantity, 0);
    const sb = b.items.reduce((s, c) => s + c.quantity, 0);
    if (sb !== sa) return sb - sa;
    return a.wpName.localeCompare(b.wpName);
  });
}
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd web && npx vitest run lib/__tests__/review-group.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 6: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add web/lib/types.ts web/lib/review-group.ts web/lib/__tests__/review-group.test.ts
git commit -m "feat(review): groupCardsByL7 + ReviewItem.l7_label (등록 카드 l7 그룹핑 순수함수, TDD)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: registered route — l7_label 도출 (master backfill)

**Files:**
- Modify: `web/app/api/mock/review/registered/route.ts`

> 이 변경은 실 DB(COALESCE/MAX/JOIN 거동)에 의존하므로 단위 모킹이 아니라 **실 API curl 로 결정론 검증**한다 (모킹은 SQL 자체를 검증 못 함 — 기존 `transforms.test.ts` 도 PG 의존분은 동일 분리).

- [ ] **Step 1: 쿼리 + item 매핑 수정**

`web/app/api/mock/review/registered/route.ts` 의 `rows` 쿼리를 아래로 교체 (master_l7 CTE + l7_label 추가, 기존 SELECT/필터/GROUP BY/ORDER BY 유지):

```ts
  const rows = (await (sql as any)`
    WITH master_l7 AS (
      SELECT wa, l6_main, l7_5_activity, MAX(NULLIF(l7_sub,'')) AS m_l7
      FROM activity_master WHERE site_id = ${siteId}
      GROUP BY wa, l6_main, l7_5_activity
    )
    SELECT ma.wa, ma.l6_main,
           COALESCE(NULLIF(ma.l7_5_activity,''),'미분류') AS l75_label,
           COALESCE(MAX(NULLIF(ma.l7_sub,'')), MAX(ml.m_l7), '기타') AS l7_label,
           ROUND(SUM(ma.today_qty)::numeric,2) AS cum_qty,
           MAX(ma.unit) AS unit,
           MAX(ma.company) AS company,
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
  `) as Array<{
    wa: string | null; l6_main: string | null; l75_label: string; l7_label: string;
    cum_qty: number | string | null; unit: string | null;
    company: string | null; company_n: number | string;
  }>;
```

`items` 매핑에 `l7_label` 추가 (기존 객체에 한 줄):

```ts
      wa: r.wa, l6_main: r.l6_main, confidence: 1.0,
      status: "confirmed", alternative_wps: [],
      l7_label: r.l7_label,
```

- [ ] **Step 2: 실 API 검증 (결정론 before/after)**

dev 서버 자동 reload 후:

Run:
```bash
curl -s "http://localhost:5537/api/mock/review/registered?wa=FAB&l6=%EC%B2%A0%EA%B7%BC%EC%BD%98%ED%81%AC%EB%A6%AC%ED%8A%B8%EA%B3%B5%EC%82%AC" \
 | /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -c "import sys,json,collections; d=json.load(sys.stdin); c=collections.Counter(i['l7_label'] for i in d['items']); print('total',d['total']); [print(k,v) for k,v in c.most_common()]"
```
Expected (정답):
```
total 47
콘크리트공사 29
철근공사 9
PSRC 공사 6
거푸집공사 3
```
→ 모든 item 에 `l7_label` 존재(없음/None 0건), 합 47, master backfill 로 빈 l7_sub 도 거푸집/철근/콘크리트로 분류됨.

- [ ] **Step 3: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add web/app/api/mock/review/registered/route.ts
git commit -m "feat(review/registered): l7_label 도출 (mapper.l7_sub > master_l7 JOIN > 기타)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: review/page.tsx — 등록 모드 l7 그룹핑 분기

**Files:**
- Modify: `web/app/(app)/review/page.tsx:9` (import), `:93-96` (groups useMemo)

- [ ] **Step 1: import + 분기 수정**

import 라인(`:9`)에 `groupCardsByL7` 추가:
```ts
import { groupCardsByWp, groupCardsByL7 } from "@/lib/review-group";
```

`groups` useMemo(`:93`) 를 등록/HIL 분기로 교체:
```ts
  // HIL 은 cards 전체(확정 포함)를 (wa,l6) 그룹핑. 등록은 registered 를 l7(l7_sub) 그룹핑.
  const groups = useMemo(
    () => (onlyUnconfirmed ? groupCardsByWp(cards) : groupCardsByL7(registered)),
    [onlyUnconfirmed, cards, registered]
  );
```

- [ ] **Step 2: 라이브 UI 검증 (playwright)**

Run: review 페이지(`:5537/review`) → 좌측 FAB>건축>철근콘크리트공사 선택 → 우측 그린 헤더가 **거푸집공사 / 철근공사 / 콘크리트공사 / PSRC 공사** 4개로 분리되고 각 헤더 "등록 3·9·29·6건" 표시되는지 스크린샷 확인. (점유 시 mcp-chrome 종료 후 사용)
Expected: 한 통 47 평면 → 4 l7 그룹. 헤더 부제 path = "M15X Ph-3 IBL > FAB > 철근콘크리트공사".

- [ ] **Step 3: HIL 모드 회귀 확인 (불변)**

Run: "신규 확정 필요만 보기" 토글 ON. (라이브 requires_review=0 이면 "검토할 신규 매핑이 없습니다" 정상.) 토글로 그룹핑 함수 분기만 바뀌고 HIL 경로는 `groupCardsByWp` 그대로임을 코드/화면으로 확인.
Expected: HIL 모드 동작/markup 불변.

- [ ] **Step 4: 커밋**

```bash
cd "/Users/kyungseoplee/Project Agent/CPIA"
git add "web/app/(app)/review/page.tsx"
git commit -m "feat(review): 등록 모드 우측 카드 l7 그룹핑(groupCardsByL7) 분기 — HIL 불변

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: 전체 회귀 + 최종 검증

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: 전체 vitest 통과**

Run: `cd web && npm test`
Expected: 전체 PASS (review-group.test 신규 4 + 기존 transforms 등 회귀 0).

- [ ] **Step 2: 타입 빌드 검증**

Run: `cd web && npx tsc --noEmit`
Expected: 에러 0 (l7_label optional 추가가 기존 ReviewItem 사용처 안 깨뜨림).

- [ ] **Step 3: 토목 l7 그룹 스폿체크 (실 API)**

Run:
```bash
curl -s "http://localhost:5537/api/mock/review/registered?wa=FAB&l6=%ED%86%A0%EA%B3%B5%EC%82%AC" \
 | /Users/kyungseoplee/Project\ Agent/CPIA/pipeline/.venv/bin/python -c "import sys,json,collections; d=json.load(sys.stdin); c=collections.Counter(i['l7_label'] for i in d['items']); [print(k,v) for k,v in c.most_common()]"
```
Expected: `터파기 및 되메우기` 등 l7 그룹으로 분류(빈 l7_sub 라도 master backfill). `기타` 가 대다수면 backfill 실패 신호 → 조사.

- [ ] **Step 4: 최종 상태 보고**

3개 커밋(Task1-3) + 검증 출력 원문 인용. 브랜치 `feature/review-l75-hil`, 미머지(머지전략 사용자 확인).

---

## 검증 게이트 요약 (CLAUDE.md §3 — 실행+원본출력+의미검증)
- 단위: `groupCardsByL7` 4 케이스 vitest PASS.
- 통합(결정론 loop): registered API curl → 철콘 FAB `콘크리트29/철근9/PSRC6/거푸집3=47` 원문 일치.
- 회귀: `npm test` 전체 + `tsc --noEmit`.
- 라이브: playwright 4그룹 스크린샷.

## 범위 밖 (스펙 §7)
좌측 트리 l7 레벨 / HIL 모드 l7 / 좌측 카드 grain 변경 / 보드 뷰 l7.

## 리스크
병행 세션 같은 브랜치 — 변경 4파일만 stage. `master_l7` CTE(site당 235행) 비용 무시 가능.
