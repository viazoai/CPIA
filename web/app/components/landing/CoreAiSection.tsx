import {
  Sparkles,
  Network,
  TrendingUp,
  Lightbulb,
  ArrowRight,
  Clock4,
  type LucideIcon,
} from "lucide-react";

interface CoreFeature {
  index: string;
  agent: "Mapper" | "Forecaster" | "Optimizer";
  Icon: LucideIcon;
  headline: string;
  /** 사람 작업 (AS-IS) → AI 작업 (TO-BE) 정량 비교 chip */
  shift: { from: string; to: string };
  /** AI 가 무엇을 자동화하고 사람이 무엇만 남기는지 한 단락에 정리 */
  body: string;
}

const FEATURES: CoreFeature[] = [
  {
    index: "01",
    agent: "Mapper",
    Icon: Network,
    headline: "작업일보 실적 정보 → WBS 자동 매핑",
    shift: { from: "사람 1~3h / 일", to: "AI 10 분 / 일" },
    body:
      "협력사가 작성한 작업 내용의 문맥을 파악하여 의미 기반으로 WBS 에 자동 연결합니다. " +
      "AI 가 신규 발생 작업에 대해 평균 정확도 약 92% 로 매핑하면, 사람은 확신도 낮은 8%의 작업 건만 검토하면 됩니다.",
  },
  {
    index: "02",
    agent: "Forecaster",
    Icon: TrendingUp,
    headline: "오늘의 생산성 Risk는? AI 가 자동 진단",
    shift: { from: "D+2~3 일 사후 인지", to: "D+0 당일 진단" },
    body:
      "현장의 금일 Productivity와 Impact를 기준으로 4분면 (정상·주의·위험) 으로 진단하여, 현장관리자는 별도 분석 작업 없이 위험 항목에 대해 빠르게 조치하여 현장 공기 단축에 보다 집중하여 수행할 수 있습니다.",
  },
  {
    index: "03",
    agent: "Optimizer",
    Icon: Lightbulb,
    headline: "예상 지연 공기와 만회 시나리오 동시 제공",
    shift: { from: "사후 대책 수립", to: "조기 대응 및 방안 제시" },
    body:
      "생산성을 기반하여 최적화 가능한 공사기간을 제시하고, 과거 작업 패턴을 분석하여 유사 만회 시나리오와 Catch-up Plan을 사전에 제시합니다. " +
      "현장관리자는 문제 해결에만 집중하면 됩니다.",
  },
];

/* CoreAi 는 슬라이드 발표 모드에서 3장 분할:
 *   index=0 → Mapper (+ 섹션 타이틀)
 *   index=1 → Forecaster
 *   index=2 → Optimizer
 * 각 슬라이드는 자체 글로우 + 한 feature 만 크게 표시. */
export function CoreAiFeatureSlide({ index }: { index: 0 | 1 | 2 }) {
  const f = FEATURES[index];
  // alternating flip: 0=mockup 오른쪽, 1=왼쪽, 2=오른쪽 — 발표 시 시선 변화
  const flip = index === 1;
  const isIntro = index === 0;

  return (
    <section
      id={index === 0 ? "ai-features" : undefined}
      className="relative overflow-hidden bg-card"
    >
      {/* 배경 글로우 */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 right-[10%] -z-0 h-[480px] w-[480px] rounded-full bg-brand-light/40 blur-3xl"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 left-[5%] -z-0 h-[360px] w-[360px] rounded-full bg-mint/15 blur-3xl"
      />

      <div className="relative mx-auto max-w-wrap px-6 md:px-10">
        {/* 섹션 eyebrow + 진행 표기 (Core AI · 0X / 03) */}
        <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          <span>/ 03 — Core AI</span>
          <span className="text-ink-light">·</span>
          <span className="font-mono text-ink-light">
            {f.index} <span className="text-ink-light/60">/ 03</span>
          </span>
        </div>

        {/* 첫 슬라이드에만 섹션 타이틀 표시 — 후속 슬라이드는 feature 에 집중 */}
        {isIntro && (
          <div className="mt-3 max-w-3xl">
            <h2 className="font-display text-h3 text-ink">
              CPIA, 어떻게{" "}
              <span className="text-brand">사람을 대신</span>하는가
            </h2>
            <p className="mt-4 text-body text-ink-mid">
              시스템으로는 대체 불가능한 사람이 필요한 판단·해석 영역을 아래 세 가지 CORE AI가 직접 수행합니다.
            </p>
          </div>
        )}

        <div className={isIntro ? "mt-8" : "mt-4"}>
          <FeatureRow feature={f} flip={flip} large />
        </div>
      </div>
    </section>
  );
}

function FeatureRow({
  feature,
  flip,
  large,
}: {
  feature: CoreFeature;
  flip: boolean;
  /** 슬라이드 1장에 한 feature 만 있을 때 — mockup 크기 확대 */
  large?: boolean;
}) {
  const { Icon } = feature;
  const mockMax = large ? "max-w-md" : "max-w-sm";

  return (
    <div className="grid items-center gap-12 md:grid-cols-2 md:gap-16">
      {/* TEXT */}
      <div className={flip ? "md:order-2" : ""}>
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-brand-light text-brand-text">
            <Icon className="h-5 w-5" />
          </span>
          <span className="font-display text-h5 font-semibold text-brand-text">{feature.agent}</span>
        </div>
        <h3 className="mt-3 font-display text-h4 text-ink">{feature.headline}</h3>

        {/* 정량 대치 — 사람 → AI 한 줄 칩 */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center rounded-full bg-rose-light px-3 py-1 text-body-sm font-medium text-rose-text">
            {feature.shift.from}
          </span>
          <ArrowRight className="h-4 w-4 text-ink-light" />
          <span className="inline-flex items-center gap-1 rounded-full bg-mint-light px-3 py-1 text-body-sm font-semibold text-mint-text">
            <Sparkles className="h-3 w-3" />
            {feature.shift.to}
          </span>
        </div>

        <p className="mt-5 text-body text-ink-mid">{feature.body}</p>
      </div>

      {/* IMAGE / MOCKUP */}
      <div className={`${flip ? "md:order-1 md:justify-self-start" : "md:justify-self-end"} mx-auto w-full ${mockMax}`}>
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

    </div>
  );
}

/* — Forecaster: 4분면 진단 카드 — */
function ForecasterMock() {
  // KPI 와 1:1 일치 — 정상 9 · 주의 3 (좌상 + 우하 대각 분포) · 위험 2 (today 펄스 overlay)
  const dots: { x: number; y: number; tone: "ok" | "warn" | "risk" }[] = [
    // 정상 (좌하단) — 9개
    { x: 12, y: 12, tone: "ok"   },
    { x: 22, y: 28, tone: "ok"   },
    { x: 38, y: 18, tone: "ok"   },
    { x: 18, y: 38, tone: "ok"   },
    { x: 30, y: 30, tone: "ok"   },
    { x: 42, y: 22, tone: "ok"   },
    { x: 8,  y: 22, tone: "ok"   },
    { x: 35, y: 8,  tone: "ok"   },
    { x: 28, y: 45, tone: "ok"   },
    // 주의 (좌상 + 우하 대각) — 3개
    { x: 22, y: 72, tone: "warn" }, // 좌상
    { x: 32, y: 88, tone: "warn" }, // 좌상
    { x: 78, y: 28, tone: "warn" }, // 우하 (구 관찰 → 주의)
    // 위험 (우상단) — 2개 · 두 번째 점 위에 today 펄스 overlay
    { x: 90, y: 90, tone: "risk" },
    { x: 82, y: 78, tone: "risk" },
  ];
  const dotColor = (t: "ok" | "warn" | "risk") =>
    t === "ok"   ? "bg-mint"
    : t === "warn" ? "bg-sun"
    :                "bg-rose";

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
          {/* 4 quadrant background fills — 좌상/우하 모두 주의 (대각 동톤) */}
          <span aria-hidden className="absolute left-0 top-0 h-1/2 w-1/2 bg-sun-light/45"  />   {/* 주의   */}
          <span aria-hidden className="absolute right-0 top-0 h-1/2 w-1/2 bg-rose-light/55" />   {/* 위험   */}
          <span aria-hidden className="absolute left-0 bottom-0 h-1/2 w-1/2 bg-mint-light/45" />  {/* 정상   */}
          <span aria-hidden className="absolute right-0 bottom-0 h-1/2 w-1/2 bg-sun-light/45" /> {/* 주의 (구 관찰) */}
          {/* axes */}
          <div className="absolute inset-y-0 left-1/2 w-px bg-border-soft" />
          <div className="absolute inset-x-0 top-1/2 h-px bg-border-soft" />
          {/* quadrant labels */}
          <span className="absolute left-2 top-1.5 font-mono text-[9px] uppercase tracking-wider text-sun-text">주의</span>
          <span className="absolute right-2 top-1.5 font-mono text-[9px] uppercase tracking-wider text-rose-text">위험</span>
          <span className="absolute left-2 bottom-1.5 font-mono text-[9px] uppercase tracking-wider text-mint-text">정상</span>
          <span className="absolute right-2 bottom-1.5 font-mono text-[9px] uppercase tracking-wider text-sun-text">주의</span>
          {/* dots */}
          {dots.map((d, i) => (
            <span
              key={i}
              className={`absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white shadow-sm ${dotColor(d.tone)}`}
              style={{ left: `${d.x}%`, top: `${100 - d.y}%` }}
            />
          ))}
          {/* highlight today — 우측 상단 위험 분면, 빨간 점 + 펄스 ring */}
          <span
            aria-hidden
            className="absolute h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose/30 animate-ping"
            style={{ left: "82%", top: "22%" }}
          />
          <span
            className="absolute h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-rose ring-2 ring-white shadow-md"
            style={{ left: "82%", top: "22%" }}
          />
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

    </div>
  );
}
