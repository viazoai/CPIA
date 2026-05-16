# CPIA 디자인 시스템 — Handover Spec

> Layer 1 (현장 현황) 화면에서 정립된 시각 시스템. 다른 화면(Layer 2 · H-i-L Modal 등)을 만들 때 **이 문서를 단일 출처로 본다**. 새 토큰·컴포넌트가 필요해지면 코드 추가 + 본 문서 갱신을 **같은 PR 에서** 처리.

- **레포**: https://github.com/viazoai/CPIA
- **트랙**: B_Track (web/, infra/)
- **현재 시점 commit**: `ef08ff4` 기준
- **dev**: `cd web && npm run dev` → `http://127.0.0.1:5535`
- **참조 시안**: `design/CPIA_기획서_v7.1.html`

---

## 1. Stack

| 영역 | 선택 |
|---|---|
| Framework | **Next.js 14.2.35 (App Router)** + React 18 + TypeScript 5 |
| Styling | **Tailwind CSS 3.4** + CSS 변수 (HSL · v7.1 hex 혼합) |
| 컴포넌트 primitive | **shadcn/ui** (selective install · Radix-ui 기반) |
| 아이콘 | **lucide-react** |
| 유틸 | `clsx` + `tailwind-merge` (`cn(...)` 헬퍼) + `class-variance-authority` |
| 애니메이션 | `tailwindcss-animate` plugin |

**왜 이 조합**: v7.1 시안의 한국어·임원 보고서 톤을 살리되, 인터랙티브 컴포넌트(Dialog·Modal·Tabs) 는 검증된 primitive(shadcn) 위에서 안전하게 구성. Geist 폰트는 한글 글리프 부족으로 폐기, Pretendard+Noto Sans KR 사용.

---

## 2. 디자인 토큰

### 2-1. 색 — 의미별 6 톤 × 3 단계

각 의미 색은 **light (배경) · DEFAULT (강조) · text (어두운 텍스트)** 3 단계. tailwind 클래스로 직접 사용 가능.

| 의미 | 용도 | light | DEFAULT | text |
|---|---|---|---|---|
| **mint** | 정상·성공·긍정 변화 | `bg-mint-light` `#e3f9f0` | `bg-mint` `#0ea76a` | `text-mint-text` `#075c3c` |
| **sun** | 주의·경계 | `bg-sun-light` `#fef3c7` | `bg-sun` `#d97706` | `text-sun-text` `#92400e` |
| **rose** | 위험·destructive | `bg-rose-light` `#fee2e2` | `bg-rose` `#ef4444` | `text-rose-text` `#b91c1c` |
| **lavender** | primary·강조 액션 | `bg-lavender-light` `#e8eeff` | `bg-lavender` `#1a56db` | `text-lavender-text` `#1243a8` |
| **sky** | 정보·중립 데이터 | `bg-sky-light` `#dbeafe` | `bg-sky` `#2563eb` | `text-sky-text` `#1d4ed8` |
| **peach** | 이벤트·데모·warm chip | `bg-peach-light` `#fef0eb` | `bg-peach` `#e55c2b` | `text-peach-text` `#a13a14` |

> **status 매핑 룰** (절대 어기지 않음):
> - `normal` → `mint`
> - `caution` → `sun`
> - `risk` → `rose`
> - `unknown` → `surface-soft + ink-light`

### 2-2. 색 — 텍스트·면 (위계)

```
ink            #0d1117   (헤더·핵심 수치)
ink-mid        #444e5e   (본문)
ink-light      #7a8494   (보조·라벨)

surface        #ffffff   (페이지 배경 — body)
surface-card   #ffffff   (카드 면)
surface-soft   #f8f9fb   (pain box · footer · disabled)

border         #e2e6ed   (기본 윤곽)
border-soft    #eef0f4   (얇은 구분 · 카드 외곽)
```

### 2-3. shadcn HSL 변수 (primitive 컴포넌트 자동 매핑)

shadcn `<Button>` `<Card>` 등이 자동으로 v7.1 톤을 따라가도록 globals.css 에 HSL 매핑:

```
--primary       → lavender-deep   (220 76% 48%)
--accent        → mint-deep       (152 88% 35%)
--destructive   → rose-deep       (0 84% 60%)
--background    → bg              (0 0% 100%)
--foreground    → ink             (220 39% 6%)
--card          → bg-card
--muted         → bg-soft
--border        → border
--ring          → primary (focus)
```

**중요**: `border` 는 객체 토큰 (`{ DEFAULT, soft }`) 으로 정의되어 shadcn 의 `border-border` 와 우리의 `border-border-soft` **둘 다 풀린다**. 새 키 추가 시 같은 패턴 유지.

### 2-4. 폰트 위계

| 클래스 | 폰트 | 사용 시점 |
|---|---|---|
| `font-sans` (default) | **Pretendard** + Noto Sans KR + system | 모든 본문·기본 텍스트 |
| `font-display` | **Space Grotesk** + Pretendard | 헤더, 큰 숫자(`text-3xl+`), 영문 강조 |
| `font-mono` | **JetBrains Mono** | 코드, 작은 라벨(`/01`), site_id, 수치 단위 |

### 2-5. 반경·그림자·여백

| 토큰 | 값 | 용도 |
|---|---|---|
| `rounded-card` | 18px | 표준 카드 |
| `rounded-card-lg` | 24px | 큰 컨테이너 |
| `rounded-card-xl` | 32px | 특별 hero 영역 |
| `rounded-md` | 8px | shadcn 기본 (Badge·Button) |
| `rounded-full` | — | 칩·dot·indicator |
| `shadow-xs` | `0 1px 2px rgba(13,17,23,0.04)` | 평소 카드 |
| `shadow-sm` | `0 2px 8px rgba(13,17,23,0.06)` | hover |
| `shadow-md` | `0 6px 28px rgba(13,17,23,0.11)` | Modal·Sheet |
| `shadow-lg` | `0 16px 48px rgba(13,17,23,0.16)` | 최상단 띄움 |
| `max-w-wrap` | 1240px | 메인 컨텐츠 컨테이너 |

### 2-6. 배경 라디얼 blob

`<body>::before/::after` 에 lavender + mint radial gradient blob 2 개. 임원 보고서 톤. 모든 페이지에 자동 적용. **건드리지 말 것**.

---

## 3. 컴포넌트 라이브러리

### 3-1. shadcn primitive (현재 install)

| 컴포넌트 | 경로 | 변형 |
|---|---|---|
| `Button` | `components/ui/button.tsx` | `default` · `outline` · `ghost` · `link` · `destructive` · `secondary` |
| `Card` | `components/ui/card.tsx` | `<Card>`+`<CardHeader>`+`<CardContent>`+`<CardFooter>`+`<CardTitle>`+`<CardDescription>` |
| `Badge` | `components/ui/badge.tsx` | `default` · `outline` · `secondary` · `destructive` |
| `Separator` | `components/ui/separator.tsx` | `orientation="horizontal" \| "vertical"` |

**import 패턴**:
```tsx
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
```

### 3-2. 추가 add 예정 (즉시 사용 가능 — 필요 시 한 줄 CLI)

```bash
cd web
npx shadcn@latest add dialog sheet tabs sonner
```

| 컴포넌트 | 용도 |
|---|---|
| `Dialog` | **H-i-L 1 (Mapper 검토) Modal · H-i-L 2 (Trade 선택) Modal** |
| `Sheet` | Layer 2 사이트 상세 side panel (모바일·태블릿 우선) |
| `Tabs` | Layer 2 안의 섹션 전환 (전체·공종·BP사 등) |
| `Sonner` (toast) | 매핑 수정 완료·파이프라인 재개 알림 |

> add 후 본 문서 §3-1 표에 추가 + 사용 패턴 §5 에 예시 박기.

### 3-3. 우리가 만든 도메인 컴포넌트

| 컴포넌트 | 경로 | 책임 |
|---|---|---|
| `<Kpi>` | `app/page.tsx` 내부 | KPI 1 칸 — tone(아이콘+색 stripe)·label·value·sub |
| `<TopBar>` | `app/components/TopBar.tsx` | 페르소나 토글 + 브랜드 |
| `<Sidebar>` | `app/components/Sidebar.tsx` | 5 메뉴, 페르소나별 필터 |
| `<PersonaToggle>` | `app/components/PersonaToggle.tsx` | 구성원/관리자 switch |
| `<Hero>` `<NowStrip>` `<AgentCard>` `<HilReviewStage>` | `app/components/home/` | Home 4 컴포넌트 |
| `<DailyRunList>` `<AgentProgressList>` `<AgentChatLog>` | `app/components/tasks/` | Agent Tasks 3 컴포넌트 |
| `<WBSTree>` `<ReviewCard>` `<WPSearchCombobox>` | `app/components/review/` | Human Review 3 컴포넌트 |
| `<ReportDailyList>` `<KpiStrip>` `<ForecastTab>` `<OptimizeTab>` `<OptimizerResult>` `<QuadrantCountKpi>` `<RawDataTab>` | `app/components/reports/` | Report 7 컴포넌트 |
| `<PerformanceTab>` `<ImpactTab>` `<SiteOverviewCard>` `<HorizontalBarList>` | `app/components/dashboard/` | Dashboard 4 컴포넌트 |
| `<SCurveChart>` `<BarChartH>` `<QuadrantScatter>` `<TrendLineChart>` | `app/components/charts/` | recharts 차트 4종 |

---

## 4. 아이콘 사용 (lucide-react)

전체 1000+ 아이콘 풀. **import 한 번에 하나씩** (tree-shake).

### 4-1. 화면별 표준 매핑

| 위치 | 아이콘 | 이유 |
|---|---|---|
| Brand dot | `Sparkles` | AI 의도 표현 |
| 전체 현장 KPI | `Building2` | 건설 도메인 |
| 상태 분포 KPI | `AlertOctagon` | 경계 신호 |
| 시간 KPI | `Clock4` | 시계 |
| FTE KPI | `UsersRound` | 인력 |
| Status: normal | `CheckCircle2` | 합격 |
| Status: caution | `AlertTriangle` | 주의 |
| Status: risk | `Flame` | 긴급 |
| Trend up | `TrendingUp` | 진척 양호 |
| Trend down | `TrendingDown` | 지연 |
| 마지막 실행 | `Clock` | 시간 |
| 상세 버튼 | `ArrowRight` | 이동 |

> 새 위치에 아이콘 추가 시 본 표에 추가. 같은 의미는 같은 아이콘.

### 4-2. 사용 예

```tsx
import { Sparkles } from "lucide-react";

<Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
```

- 크기: `h-3 w-3` (inline) · `h-4 w-4` (KPI·버튼) · `h-5 w-5` 이상 (드물게)
- `strokeWidth={2}` 가 기본. 강조 시 2.5

---

## 5. 사용 패턴 (코드 예시)

### 5-1. Status chip (Badge)

```tsx
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

<Badge
  variant="outline"
  className={cn(
    "inline-flex h-6 items-center gap-1 px-2 text-[11px] font-semibold",
    "bg-sun-light text-sun-text border-transparent"  // caution
  )}
>
  <AlertTriangle className="h-3 w-3" />
  주의
</Badge>
```

→ STATUS_STYLE 룩업 테이블 패턴 (SiteCard.tsx 참조) 적극 사용.

### 5-2. Numbered eyebrow (헤더 위 작은 label)

```tsx
<div className="flex items-center gap-3">
  <span className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-lavender-text">
    / 01 — Hi-tech 사업부
  </span>
  <span className="h-px w-8 bg-border" />
  <span className="font-mono text-[11px] uppercase tracking-widest text-ink-light">
    현장 현황
  </span>
</div>
```

### 5-3. Gradient text (헤더 일부 강조)

```tsx
<h1 className="font-display text-4xl font-bold leading-[1.15] tracking-tight text-ink md:text-5xl">
  <span>작업일보 →</span>{" "}
  <span className="bg-gradient-to-r from-lavender to-mint bg-clip-text text-transparent">
    AI 파이프라인
  </span>{" "}
  <span>→ 생산성 진단</span>
</h1>
```

### 5-4. Color stripe top (카드 식별)

```tsx
<div className="relative overflow-hidden rounded-card border border-border-soft bg-card p-5 shadow-xs">
  <span
    aria-hidden
    className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-lavender to-lavender opacity-90"
  />
  {/* … 콘텐츠 … */}
</div>
```

### 5-5. Status stripe left (카드 우선순위)

```tsx
<Card className="relative overflow-hidden rounded-card">
  <span
    aria-hidden
    className="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-rose/80 to-rose"
  />
  {/* CardHeader pl-7 부터 시작 (stripe 폭만큼 padding) */}
</Card>
```

### 5-6. 진행률 막대

```tsx
<div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-soft">
  <div
    className="h-full bg-mint transition-all"
    style={{ width: `${Math.min(value, 100)}%` }}
  />
</div>
```

### 5-7. Live indicator (nav 우측 등)

```tsx
<Badge variant="outline" className="gap-1 border-border bg-white px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-ink-mid">
  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
  live · 5535
</Badge>
```

### 5-8. KPI 카드 골격 (재사용 컴포넌트)

`app/page.tsx` 의 `<Kpi>` 함수 참조. tone 별 stripe + 아이콘 박스 + 큰 숫자 + 색 sub.

---

## 6. 페이지 구조 패턴

### 6-1. 표준 페이지 레이아웃

```tsx
<div className="relative min-h-screen">
  {/* sticky nav */}
  <nav className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border bg-white/85 px-6 backdrop-blur-md md:px-10">
    {/* brand · 우측 chip */}
  </nav>

  {/* 헤더 */}
  <header className="mx-auto max-w-wrap px-6 pb-2 pt-14 md:px-10 md:pt-20">
    {/* eyebrow · h1 · description */}
  </header>

  {/* KPI grid */}
  <section className="mx-auto max-w-wrap px-6 pt-8 md:px-10">
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {/* <Kpi /> × 4 */}
    </div>
  </section>

  {/* 메인 콘텐츠 */}
  <section className="mx-auto max-w-wrap px-6 py-10 md:px-10 md:py-12">
    {/* section heading + grid */}
  </section>

  <footer className="mx-auto max-w-wrap border-t border-border-soft px-6 pb-16 pt-6 md:px-10">
    {/* metadata */}
  </footer>
</div>
```

### 6-2. 카드 그리드

```tsx
<div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
  {items.map((it) => (<Card key={it.id} {…} />))}
</div>
```

### 6-3. Section heading

```tsx
<div className="mb-6 flex items-baseline justify-between">
  <div className="flex items-baseline gap-3">
    <h2 className="font-display text-lg font-bold tracking-tight text-ink md:text-xl">
      현장별 진척 · 상태
    </h2>
    <span className="font-mono text-[10px] uppercase tracking-widest text-ink-light">
      {n} sites
    </span>
  </div>
  {/* 우측 hint */}
</div>
```

---

## 7. 데이터 (mock)

- `data/mock_sites.json` — 6 개 현장 (`청주 M15X IBL` = 실 PoC, 나머지 5 = mock)
- 타입: `Site` (`web/app/components/SiteCard.tsx` 에서 export)
- 페이지에서 `fs.readFile` 로 직접 로드 (서버 컴포넌트)

```tsx
import { promises as fs } from "fs";
import path from "path";

async function loadMockSites(): Promise<Site[]> {
  const p = path.join(process.cwd(), "..", "data", "mock_sites.json");
  return JSON.parse(await fs.readFile(p, "utf-8"));
}
```

> **A_Track 데이터 통합 전까지** mock_sites.json 이 단일 출처. Postgres `sites` 테이블 seed 는 A 가 PoC 1 row, B 가 mock 5 row 적재 (예정).

---

## 8. Do / Don't

### Do
- 의미 색은 **STATUS 매핑** (mint=normal · sun=caution · rose=risk) 절대 어기지 않기
- 새 컬러 필요하면 globals.css 의 `:root` 에 변수 추가 + tailwind.config 에 토큰 박기 + 본 문서 갱신
- shadcn primitive 위에 도메인 컴포넌트 쌓기 (직접 raw HTML 지양)
- `cn(...)` 으로 조건부 className (직접 `${...}` 템플릿 X)
- 아이콘은 **lucide-react 만** (다른 아이콘 라이브러리 추가 금지)
- 모든 페이지 max-width: `max-w-wrap` (1240px)

### Don't
- ❌ 임의의 hex 색 inline (예: `style={{ color: "#ff0000" }}`) — 토큰 우회
- ❌ 새 폰트 추가 (한국어 + 영문 가독성 3 fam 이미 충분)
- ❌ shadcn primitive 의 base 클래스 (`bg-primary`, `text-foreground` 등) 를 의미 색으로 덮기 — primary 는 lavender 매핑이 정해진 상태, 다른 의미로 쓰지 말 것
- ❌ Tailwind v4 문법 (`@theme` 등) — 우리는 v3.4 고정
- ❌ Geist 폰트 재추가 (한글 글리프 부족으로 폐기)
- ❌ 카드를 흰 사각형으로만 두기 — 좌측 stripe / 상단 stripe / 아이콘 박스 중 하나는 시각 신호로

---

## 9. 후속 작업 (Phase 2 — A_Track 연결)

| 영역 | 현재 | 다음 단계 |
|---|---|---|
| Mock fixture → 실 API | `web/lib/fixtures.ts` 가 `data/mock_*.json` 로드 | A_Track GATE 통과 시 `web/app/api/mock/*` 라우트의 `loadFixture` 호출을 실제 Postgres SELECT / FastAPI proxy 로 swap. mock 과 실 API 의 응답 shape 이 같으므로 컴포넌트는 변경 없음. |
| 현장별 detail 확장 | M15X 만 fixture 채워짐 (PoC 시연 우선) | 다른 5 현장의 detail 도 fixture 또는 실 데이터로 보강 |
| Dashboard 14일 히트맵 | 보류 (spec §10-2) | 사용자 요청 시 wireframe v2 |
| Daily Report 풀스크린 페이지 | 보류 (엑셀 산출물로 충분) | 사용자 요청 시 추가 |

---

## 10. 참조 파일 (소스)

```
docs/ui/design-system.md       ← 본 문서
design/CPIA_기획서_v7.1.html   ← 원 시안 (시각 톤 참조 단일 출처)
data/mock_sites.json           ← 화면 데이터 mock

web/
├── app/
│   ├── globals.css            ← CSS 변수 (v7.1 + shadcn HSL)
│   ├── layout.tsx             ← 폰트 + lang=ko
│   ├── page.tsx               ← Layer 1 + <Kpi> 컴포넌트
│   └── components/
│       └── SiteCard.tsx       ← 도메인 카드 (참조 예시)
├── components/ui/             ← shadcn primitive (수정 가능, 같은 패턴 유지)
│   ├── button.tsx
│   ├── card.tsx
│   ├── badge.tsx
│   └── separator.tsx
├── lib/utils.ts               ← cn() 헬퍼
├── tailwind.config.ts         ← 토큰 정의
├── components.json            ← shadcn CLI 설정
└── package.json
```

---

*최종 수정: 2026-05-16 · 5 화면 구현 완료 + 신규 컴포넌트 30+개 등록*
*다음 갱신: A_Track 데이터 연결 (Phase 2 진입) 시점*
