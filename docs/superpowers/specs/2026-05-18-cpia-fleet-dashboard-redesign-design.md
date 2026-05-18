# CPIA — Fleet Dashboard 재구성 (전사 현장 모니터링)

> /reports v3 의 분석 패턴을 fleet 레벨로 끌어올려 임원·발주처가 전사 현장 6개의 생산성·추세·이슈를 한 화면에서 즉시 파악할 수 있는 모니터링 대시보드로 재구성한다.

---

## 1. 목적과 범위

### 목적
- 현재 `/dashboard` 는 Performance (생산성 KPI + 현장 카드 grid) / Impact (Middle Office 절감) 두 탭을 가지고 있지만, 시각화가 단순 카드 grid 위주라 "전사 차원의 추세·이상 신호" 가 약하다.
- /reports v3 에서 정립된 정보 위계 (KPI → 시계열 → 개별 진입) 패턴을 fleet 레벨에 그대로 적용해 **전사 모니터링 화면** 으로 격상한다.

### 범위
- **포함**: `/dashboard` 페이지의 Performance 탭 재구성, 시계열 차트 신규, 현장 카드 sparkline 추가, `/dashboard/sites/[id]` 페이지 제거.
- **제외**: 프로젝트별 대시보드 (`/dashboard/sites/[id]`) 는 PoC 범위 밖으로 제외. Impact 탭은 현 구조 유지 (변경 없음).

### 두 영역의 관계
| 탭 | 관점 | 주체 |
|---|---|---|
| Performance | 현장 BP 생산성 최적화 | 6개 현장 BP사 |
| Impact | Middle Office 자동화 효과 | SK에코플랜트 본사 운영 조직 |

두 영역은 청중·KPI·해석 흐름이 다르지만 둘 다 fleet 단위 결론이라 동일 페이지 안 Tabs 로 유지한다.

---

## 2. 아키텍처

```
/dashboard (단일 페이지)
├── PageHeader  / 05 — Dashboard · Fleet / 전사 현장 모니터링
└── Tabs
    ├── Performance Tab
    │   ├── § 01  Fleet KPI 4 (KpiStrip)
    │   ├── § 02  전사 생산성 시계열 (FleetProductivityTrendChart — 신규)
    │   └── § 03  현장 카드 grid (SiteOverviewCard + sparkline)
    └── Impact Tab (현 구조 유지)
        ├── KPI 4
        ├── 연간 환산 chip
        ├── 현장별 절감 분포 (HorizontalBarList)
        └── 월간 누적 트렌드 (TrendLineChart)
```

### 화면 흐름 — Performance 탭 (위 → 아래)
1. **§ 01 결론** — 전사 평균 생산성 / 평균 공기 격차 / 이상 공종 / 회복 가능 공기. 임원이 1초 안에 "전사 숨" 의 지표 파악.
2. **§ 02 추세** — 90일 동안 전사 평균 생산성이 어떤 방향으로 움직였는지, 그리고 현장 간 분포가 어느 정도 벌어졌는지. 평균선 + min~max 분포 밴드.
3. **§ 03 개별 진단 카드** — 6개 현장 각각의 현재 상태 + 미니 sparkline. 임원이 "어느 현장에서 무엇이 일어나고 있는지" 한 눈에. (이번 PoC 에서 클릭은 비활성, 카드 자체가 종착)

---

## 3. Performance 탭 상세

### § 01 — Fleet KPI 4 (현행 유지)
`PerformanceTab.tsx` 의 기존 KPI 4개 항목을 그대로 유지.

| 라벨 | 값 | 단위 | tone |
|---|---|---|---|
| 전사 평균 생산성 | `fleetKpi.avg_productivity` | % | normal |
| 평균 공기 격차 | `+fleetKpi.avg_delay` | 일 | risk |
| 이상 공종 총합 | `fleetKpi.abnormal_total` | 건 | risk |
| 회복 가능 공기 | `-fleetKpi.recoverable_days` | 일 | primary |

`KpiStrip` 컴포넌트 그대로 사용.

### § 02 — 전사 생산성 시계열 (신규)

**컴포넌트:** `FleetProductivityTrendChart.tsx`

**시각 구성** (참조: `/reports` 의 `ProductivityTrendChart` 톤 — 같은 헤더·KPI 패턴 + Area + ReferenceLine):

- 박스: `rounded-card border border-border-soft bg-card p-4 shadow-xs`
- 헤더: `font-display text-base font-semibold text-ink` "전사 생산성 추세 ({endDate} 기준)"
- 우측 KPI: `text-h3 font-semibold text-ink` 오늘 전사 평균 % + `text-base text-ink-mid` 보조 ("현장 6개 평균" 등)
- 차트 (`ResponsiveContainer height={240}`, `ComposedChart`):
  - `Area dataKey="max"` → fillOpacity 0.15, stroke none (분포 밴드 상단)
  - `Area dataKey="min"` → fill #ffffff, fillOpacity 1, stroke none (분포 밴드 하단을 흰색으로 덮어 밴드 효과)
  - `Line dataKey="mean"` stroke #1a56db width 2.5, dot=false (전사 평균선)
  - `ReferenceLine y={historyMean}` stroke #ef4444 dashed 5-4, Label "이력 평균"
  - `ReferenceDot` 마지막 평균 시점

**데이터 인터페이스:**
```ts
interface FleetTrendPoint {
  date: string;       // ISO YYYY-MM-DD
  mean: number;       // 6개 현장 평균 생산성
  min: number;        // 가장 낮은 현장
  max: number;        // 가장 높은 현장
}
```

`FleetTrendPoint[]` 90일 — `mock_dashboard.json` fixture 에 정적 시드 데이터 추가. 결정적 PRNG (mulberry32) 으로 생성해 시연마다 동일 곡선.

### § 03 — 현장 카드 grid

**기존 `SiteOverviewCard.tsx` 수정:**

1. **클릭 비활성** — 카드의 wrapping `Link`/`button` 제거, `cursor-default`, hover 효과는 그림자 정도만 약하게.
2. **mini sparkline 추가** — 카드 우측 또는 하단에 `width≈100 height≈32` 단순 line (recharts `LineChart` 또는 SVG path). 90일 데이터, dot 없음, 색은 현장 status tone.
3. **카드 헤더에 현장 status dot** (이미 있다면 유지).

**그리드:** `grid-cols-1 md:grid-cols-2 xl:grid-cols-3`, gap-3, 6개 현장 = 2~3행.

**카드 데이터 입력:**
```ts
interface SiteOverviewCardProps {
  site: Site;
  sparklineData: number[];   // 90일 — fixture 에 site.id 키로 매핑
}
```

---

## 4. Impact 탭 — 현 구조 유지

`ImpactTab.tsx` 의 `scope="fleet"` 분기 그대로 유지. 변경 없음.

- KPI 4 (전체 근무량 / 월 절감 시간 / FTE 환산 / AI 업무 대체율)
- 연간 환산 효과 chip (mint-light 박스)
- 현장별 절감 분포 (`HorizontalBarList`)
- 월간 누적 트렌드 (`TrendLineChart`)

---

## 5. 변경되는/제거되는 파일

| 종류 | 경로 | 비고 |
|---|---|---|
| 수정 | `web/app/(app)/dashboard/page.tsx` | Tabs 구조 유지, 변화 없음 |
| 수정 | `web/app/components/dashboard/PerformanceTab.tsx` | KPI 유지 + `FleetProductivityTrendChart` 삽입 + 카드 grid 호출 시 sparkline prop 전달 |
| 수정 | `web/app/components/dashboard/SiteOverviewCard.tsx` | sparkline 추가, 클릭 비활성 |
| 신규 | `web/app/components/dashboard/FleetProductivityTrendChart.tsx` | § 02 차트 |
| 삭제 | `web/app/(app)/dashboard/sites/[id]/page.tsx` | + `[id]` 디렉토리 |
| 검토 | `web/app/api/mock/dashboard/[id]/route.ts` | 사용처 없으면 삭제 |
| 검토 | sidebar / 기타 링크에서 `sites/[id]` 참조 grep 후 제거 |
| 수정 | `data/mock_dashboard.json` 또는 `web/lib/fixtures.ts` | `fleet_trend` 90일 + `site_sparklines` Record 추가 |
| 수정 | `web/lib/types.ts` | `FleetTrendPoint` 인터페이스 추가 |
| 수정 | `web/lib/fixtures.ts` | `DashboardFixture` 에 `performance.fleet_trend`, `performance.site_sparklines` 필드 추가 |

---

## 6. 데이터 모델

### `web/lib/types.ts` 추가
```ts
export interface FleetTrendPoint {
  date: string;
  mean: number;   // 0..100
  min: number;
  max: number;
}
```

### `web/lib/fixtures.ts` `DashboardFixture.performance` 확장
```ts
performance: {
  fleet_kpi: { avg_productivity, avg_delay, abnormal_total, recoverable_days };
  fleet_trend: FleetTrendPoint[];                  // 신규 — 90일
  site_sparklines: Record<string, number[]>;       // 신규 — site_id → 90일 시계열
}
```

### mock 생성 규칙
- `fleet_trend`: 6 현장 sparkline 의 일자별 평균/min/max 를 집계. fixture 빌드 시점에 결정적으로 계산.
- `site_sparklines`: site.id 시드로 `mulberry32` PRNG → 92% base + ±4 random walk + 후반 30일에 trend(+/-) 적용. /reports `ProductivityTrendChart` 와 동일 패턴 재사용.

---

## 7. 검증

1. **빌드**: `npm run build` — 12 → 11 라우트 (sites/[id] 사라짐 1)
2. **/dashboard 진입**:
   - Performance 탭 디폴트 활성, KPI 4 → 시계열 → 카드 grid 순 노출
   - 카드 클릭 시 페이지 이동 없음 (`cursor-default`)
   - 카드 안 sparkline 6개 모두 다른 형상 (mock PRNG 다른 시드)
3. **시계열 차트**:
   - 평균선이 굵게 강조, 분포 밴드(min~max)는 옅은 영역
   - 이력 평균 ReferenceLine (rose dashed) 표시
4. **Impact 탭**: 기존과 동일 동작
5. **`/dashboard/sites/M15X-Ph3-IBL` 직접 진입**: 404
6. **모바일 반응**: KPI 4 → 2×2, 카드 grid → 1열

---

## 8. 디자인 토큰 일관성

- 모든 타이포: design-system.md §2-4 의 `text-h*` / `text-body*` / `text-btn` 의미 토큰
- 색상: rose 평균선 패턴 (#ef4444 dashed 5-4) — /reports ProductivityTrendChart 와 동일
- KPI 큰 숫자: `font-display text-h3 font-semibold tracking-[-0.015em] text-ink`
- 박스: `rounded-card border border-border-soft bg-card shadow-xs` 패턴 통일

---

## 9. 후속 작업 (이번 spec 밖)
- Performance 탭의 현장 카드를 미래에 클릭 가능하게 만들 경우 `/reports?site=<id>` 라우팅 + site selector 가 필요 (이번 PoC 제외).
- Impact 탭의 Middle Office 4기능별 자동화율 (`perFunction`) 을 fleet scope 에도 노출하는 변경은 별도 spec.
