import {
  Sparkles,
  Network,
  TrendingUp,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Clock4,
  type LucideIcon,
} from "lucide-react";

interface CoreFeature {
  index: string;
  agent: "Mapper" | "Forecaster" | "Optimizer";
  Icon: LucideIcon;
  headline: string;
  lead: string;
  aiDoes: string;
  humanDoes: string;
}

const FEATURES: CoreFeature[] = [
  {
    index: "01",
    agent: "Mapper",
    Icon: Network,
    headline: "비정형 일보를 공정표 언어로 — 의미 기반 자동 매핑",
    lead: "협력사가 자유 텍스트로 적은 작업 내용을 LLM 이 의미 단위로 해석해, 공정표 WBS Activity 에 정확히 연결합니다. 키워드 일치가 아닌 도메인 맥락 이해 기반.",
    aiDoes:
      "건설 도메인 RAG 로 후보 Activity 를 추리고, LLM 이 문맥·물량·BP사 조합을 종합해 최적 매핑을 rerank.",
    humanDoes:
      "확신도 낮은 매핑만 H-i-L Modal 에서 검토·수정. 100건 중 평균 5~8건만 사람 손이 필요.",
  },
  {
    index: "02",
    agent: "Forecaster",
    Icon: TrendingUp,
    headline: "오늘 생산성이 정상인가 — 현장 이력 기반 진단",
    lead: "절대 기준(품셈) 이 아닌, 같은 현장의 과거 유사 상황과 비교해 오늘이 정상·주의·위험·이상 중 어디인지 판단합니다.",
    aiDoes:
      "Vector DB 에 축적된 과거 작업 기록을 임베딩 유사도로 검색하고, LLM 이 4분면 진단과 근거를 함께 산출.",
    humanDoes:
      "PM 은 위험·이상 분면으로 자동 라우팅된 항목만 본다. 정상 분면은 굳이 검토하지 않아도 됨.",
  },
  {
    index: "03",
    agent: "Optimizer",
    Icon: Lightbulb,
    headline: "막힌 곳은 AI 가 먼저 — 맥락 기반 만회 시나리오 제안",
    lead: "위험 표지된 공종에 대해, 과거에 비슷한 지연을 어떻게 만회했는지를 학습한 LLM 이 현재 맥락에 맞춘 catch-up 시나리오를 제시합니다.",
    aiDoes:
      "유사 과거 패턴을 검색해 인력 재배치·공정 순서 변경·야간 작업 등 옵션을 비용·일수 추정과 함께 자동 생성.",
    humanDoes:
      "PM 은 제안 시나리오 중 실행 가능한 것을 채택·조합해 발주처 협상에 활용. 의사결정은 사람이.",
  },
];

export function CoreAiSection() {
  return (
    <section
      id="ai-features"
      className="relative overflow-hidden border-t border-border-soft bg-card py-24 md:py-32"
    >
      {/* 배경 글로우 — Hero 와 같은 분위기 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 right-[10%] -z-0 h-[480px] w-[480px] rounded-full bg-brand-light/40 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 left-[5%] -z-0 h-[360px] w-[360px] rounded-full bg-mint/15 blur-3xl"
      />

      <div className="relative mx-auto max-w-wrap px-6 md:px-10">
        {/* Header */}
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 03 — Core AI
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            AI 가 정확히 어디서, 어떻게{" "}
            <span className="text-brand">사람을 대신</span>하는가
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            7-Agent 중 사람의 판단·해석 영역을 직접 대체하는 세 가지 AI 코어를 — 시스템이 아닌
            <span className="font-semibold text-ink"> "AI 의 역할" </span>
            관점에서 풀어냅니다.
          </p>
        </div>

        {/* Feature rows */}
        <div className="mt-16 flex flex-col gap-24 md:gap-28">
          {FEATURES.map((f, i) => (
            <FeatureRow key={f.agent} feature={f} flip={i % 2 === 1} />
          ))}
        </div>
      </div>
    </section>
  );
}

function FeatureRow({ feature, flip }: { feature: CoreFeature; flip: boolean }) {
  const { Icon } = feature;

  return (
    <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
      {/* TEXT */}
      <div className={flip ? "md:order-2" : ""}>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
          Core AI · {feature.index}
        </span>
        <div className="mt-3 flex items-center gap-3">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-brand-light text-brand-text">
            <Icon className="h-4 w-4" />
          </span>
          <span className="font-display text-h5 font-semibold text-brand-text">{feature.agent}</span>
        </div>
        <h3 className="mt-3 font-display text-h4 text-ink">{feature.headline}</h3>
        <p className="mt-4 text-body text-ink-mid">{feature.lead}</p>

        {/* AI / Human 역할 비교 */}
        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          <div className="rounded-card border border-brand/30 bg-brand-light/40 p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 text-brand-text" />
              <span className="text-body-sm font-semibold text-brand-text">
                AI 가 한다
              </span>
            </div>
            <p className="mt-2 text-body-sm text-ink">{feature.aiDoes}</p>
          </div>
          <div className="rounded-card border border-border bg-card p-4">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-3.5 w-3.5 text-mint-text" />
              <span className="text-body-sm font-semibold text-ink-mid">
                사람이 한다
              </span>
            </div>
            <p className="mt-2 text-body-sm text-ink-mid">{feature.humanDoes}</p>
          </div>
        </div>
      </div>

      {/* IMAGE / MOCKUP — 텍스트 카피보다 작게, 셀 안쪽 정렬 (flip 에 따라 좌·우 끝으로) */}
      <div className={`${flip ? "md:order-1 md:justify-self-start" : "md:justify-self-end"} mx-auto w-full max-w-sm`}>
        <FeatureMock agent={feature.agent} />
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────
 * Feature 별 미니 mockup — Hero 스타일 (rotated + halo + floating subcard)
 * ────────────────────────────────────────────── */

function FeatureMock({ agent }: { agent: CoreFeature["agent"] }) {
  return (
    <div className="relative">
      <div
        aria-hidden
        className="absolute -inset-8 -z-10 rounded-card-xl bg-gradient-to-tr from-brand-light/60 via-white to-mint-light/30 blur-2xl"
      />
      {agent === "Mapper" && <MapperMock />}
      {agent === "Forecaster" && <ForecasterMock />}
      {agent === "Optimizer" && <OptimizerMock />}
    </div>
  );
}

/* — Mapper: 비정형 텍스트 → WBS 코드 매핑 카드 — */
function MapperMock() {
  const rows: { text: string; code: string; conf: number; warn?: boolean }[] = [
    { text: "철근 배근 작업 진행 80%", code: "IBL-CIV-RC-04",  conf: 96 },
    { text: "거푸집 해체 완료",         code: "IBL-CIV-FW-12",  conf: 88 },
    { text: "콘크리트 타설 60m³",       code: "IBL-CIV-CC-07",  conf: 92 },
    { text: "현장 정리 및 자재 이송",   code: "—",              conf: 41, warn: true },
  ];
  return (
    <div className="relative">
      <div className="relative rotate-1 rounded-card-lg border border-border bg-card p-5 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
            Mapping Confidence
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-light px-2 py-0.5 text-[11px] font-medium text-brand-text">
            <Network className="h-3 w-3" /> WBS Match
          </span>
        </div>
        <ol className="mt-4 flex flex-col gap-2.5">
          {rows.map((r, i) => (
            <li key={i} className="flex items-center gap-2.5 rounded-md border border-border-soft bg-surface-soft/40 px-3 py-2 text-[12px]">
              <span className="flex-1 truncate text-ink">{r.text}</span>
              <ArrowRight className="h-3 w-3 text-ink-light" />
              <span className={`font-mono text-[11px] ${r.warn ? "text-rose-text" : "text-brand-text"}`}>
                {r.code}
              </span>
              <span className={`inline-flex w-12 justify-end font-mono text-[11px] font-semibold ${r.warn ? "text-rose-text" : "text-mint-text"}`}>
                {r.conf}%
              </span>
            </li>
          ))}
        </ol>
        <div className="mt-3 flex items-center justify-between border-t border-border-soft pt-3 text-[11px]">
          <span className="text-ink-mid">자동 매핑 100건 중</span>
          <span className="font-mono font-semibold text-brand-text">
            92건 자동 · <span className="text-rose-text">8건 검토 필요</span>
          </span>
        </div>
      </div>

      {/* floating chip — H-i-L */}
      <div className="absolute -bottom-5 -left-6 -rotate-3 rounded-card border border-border bg-card px-3 py-2 shadow-md">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5 text-rose-text" />
          <span className="text-[11px] font-medium text-ink">H-i-L 검토 요청</span>
        </div>
      </div>
    </div>
  );
}

/* — Forecaster: 4분면 진단 카드 — */
function ForecasterMock() {
  // y=high → top (오늘이 위험이면 top-right). 좌표는 y 가 클수록 위로 가도록 그린다.
  const dots: { x: number; y: number; tone: "ok" | "warn" | "neutral" | "risk" }[] = [
    { x: 22, y: 22, tone: "ok"      }, // bottom-left  · 정상
    { x: 38, y: 18, tone: "ok"      },
    { x: 18, y: 32, tone: "ok"      },
    { x: 28, y: 70, tone: "warn"    }, // top-left     · 주의
    { x: 82, y: 30, tone: "neutral" }, // bottom-right · 관찰
    { x: 78, y: 78, tone: "risk"    }, // top-right    · 위험
    { x: 88, y: 88, tone: "risk"    },
  ];
  const dotColor = (t: "ok" | "warn" | "neutral" | "risk") =>
    t === "ok"   ? "bg-mint"
    : t === "warn"    ? "bg-sun-deep"
    : t === "neutral" ? "bg-ink-light"
    :                   "bg-rose-deep";

  return (
    <div className="relative">
      <div className="relative -rotate-1 rounded-card-lg border border-border bg-card p-5 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
            오늘 생산성 — 4분면 진단
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-mint-light px-2 py-0.5 text-[11px] font-medium text-mint-text">
            <TrendingUp className="h-3 w-3" /> Today
          </span>
        </div>

        {/* quadrant */}
        <div className="relative mt-4 aspect-[5/3] w-full overflow-hidden rounded-md border border-border-soft bg-white">
          {/* 4 quadrant background fills */}
          <span aria-hidden className="absolute left-0 top-0 h-1/2 w-1/2 bg-sun-light/45"  />   {/* 주의   */}
          <span aria-hidden className="absolute right-0 top-0 h-1/2 w-1/2 bg-rose-light/55" />   {/* 위험   */}
          <span aria-hidden className="absolute left-0 bottom-0 h-1/2 w-1/2 bg-mint-light/45" />  {/* 정상   */}
          <span aria-hidden className="absolute right-0 bottom-0 h-1/2 w-1/2 bg-surface-soft/70" />{/* 관찰   */}
          {/* axes */}
          <div className="absolute inset-y-0 left-1/2 w-px bg-border-soft" />
          <div className="absolute inset-x-0 top-1/2 h-px bg-border-soft" />
          {/* quadrant labels */}
          <span className="absolute left-2 top-1.5 font-mono text-[9px] uppercase tracking-wider text-sun-text">주의</span>
          <span className="absolute right-2 top-1.5 font-mono text-[9px] uppercase tracking-wider text-rose-text">위험</span>
          <span className="absolute left-2 bottom-1.5 font-mono text-[9px] uppercase tracking-wider text-mint-text">정상</span>
          <span className="absolute right-2 bottom-1.5 font-mono text-[9px] uppercase tracking-wider text-ink-light">관찰</span>
          {/* dots */}
          {dots.map((d, i) => (
            <span
              key={i}
              className={`absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white shadow-sm ${dotColor(d.tone)}`}
              style={{ left: `${d.x}%`, top: `${100 - d.y}%` }}
            />
          ))}
          {/* highlight today — 우측 상단 위험 분면 */}
          <span
            className="absolute h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose-deep ring-2 ring-white shadow-md"
            style={{ left: "82%", top: "22%" }}
          />
          <span
            className="absolute font-mono text-[10px] font-semibold text-rose-text"
            style={{ left: "calc(82% + 12px)", top: "calc(22% - 6px)" }}
          >
            오늘
          </span>
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-md bg-mint-light/60 px-2 py-1.5">
            <div className="font-mono text-[10px] uppercase tracking-wider text-mint-text">정상</div>
            <div className="font-display text-base font-semibold text-ink">9</div>
          </div>
          <div className="rounded-md bg-sun-light/60 px-2 py-1.5">
            <div className="font-mono text-[10px] uppercase tracking-wider text-sun-text">주의</div>
            <div className="font-display text-base font-semibold text-ink">3</div>
          </div>
          <div className="rounded-md bg-rose-light/70 px-2 py-1.5">
            <div className="font-mono text-[10px] uppercase tracking-wider text-rose-text">위험</div>
            <div className="font-display text-base font-semibold text-ink">2</div>
          </div>
        </div>
      </div>

      {/* floating chip — auto-route */}
      <div className="absolute -top-5 -right-6 rotate-2 rounded-card border border-brand/30 bg-card px-3 py-2 shadow-md">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-brand-text" />
          <span className="text-[11px] font-medium text-ink">
            위험 2건 → Optimizer 자동 라우팅
          </span>
        </div>
      </div>
    </div>
  );
}

/* — Optimizer: catch-up 시나리오 제안 카드 — */
function OptimizerMock() {
  const opts: { title: string; sub: string; delta: string; tone: "best" | "alt" }[] = [
    { title: "야간 작업 + 인력 +6명",       sub: "RC 4공구 집중 투입",       delta: "-3일",  tone: "best" },
    { title: "선행공정 순서 재배치",         sub: "FW → CC 병행",             delta: "-2일",  tone: "alt"  },
    { title: "외주 BP사 추가 계약",          sub: "기성 BP-12 검토",          delta: "-1일",  tone: "alt"  },
  ];
  return (
    <div className="relative">
      <div className="relative rotate-1 rounded-card-lg border border-border bg-card p-5 shadow-lg">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
            AI Catch-up 시나리오
          </span>
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-light px-2 py-0.5 text-[11px] font-medium text-brand-text">
            <Lightbulb className="h-3 w-3" /> 3 옵션
          </span>
        </div>

        <div className="mt-3 rounded-md bg-rose-light/60 px-3 py-2 text-[11px] text-rose-text">
          <strong className="font-semibold">RC 공종 — D-14 만회 가능 구간 진입</strong>
          <span className="ml-1 text-ink-mid">· 유사 과거 사례 12건 분석</span>
        </div>

        <ol className="mt-3 flex flex-col gap-2">
          {opts.map((o, i) => (
            <li
              key={i}
              className={`flex items-center gap-3 rounded-md border px-3 py-2.5 ${
                o.tone === "best"
                  ? "border-brand/40 bg-brand-light/40 shadow-sm"
                  : "border-border-soft bg-surface-soft/40"
              }`}
            >
              <span className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] font-semibold ${
                o.tone === "best" ? "bg-brand text-white" : "border border-border bg-white text-ink-light"
              }`}>
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[12px] font-semibold text-ink">{o.title}</div>
                <div className="text-[11px] text-ink-mid">{o.sub}</div>
              </div>
              <span className={`inline-flex items-center gap-0.5 font-mono text-[12px] font-semibold ${
                o.tone === "best" ? "text-brand-text" : "text-ink-mid"
              }`}>
                <Clock4 className="h-3 w-3" />
                {o.delta}
              </span>
            </li>
          ))}
        </ol>

        <div className="mt-3 flex items-center justify-between border-t border-border-soft pt-3 text-[11px]">
          <span className="text-ink-mid">의사결정</span>
          <span className="font-mono font-semibold text-brand-text">PM 채택 / 발주처 협상</span>
        </div>
      </div>

      {/* floating chip — historical match */}
      <div className="absolute -bottom-5 -right-6 rotate-2 rounded-card border border-border bg-card px-3 py-2 shadow-md">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-sky-text" />
          <span className="text-[11px] font-medium text-ink">유사 패턴 12건 학습</span>
        </div>
      </div>
    </div>
  );
}
