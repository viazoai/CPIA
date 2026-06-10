"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { ReportDailyList } from "@/app/components/reports/ReportDailyList";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import { QuadrantCountKpi } from "@/app/components/reports/QuadrantCountKpi";
import { WPSummaryTable, STATUS_DOT, STATUS_LABEL } from "@/app/components/reports/WPSummaryTable";
import { ForecastChart } from "@/app/components/charts/ForecastChart";
import { ProductivityBarToggle } from "@/app/components/reports/ProductivityBarToggle";
import { ProductivityTrendChart } from "@/app/components/charts/ProductivityTrendChart";
import { QuadrantScatter } from "@/app/components/charts/QuadrantScatter";
import { diagnose } from "@/lib/diagnosis";
import { toDiagnosisInput } from "@/lib/diagnosis-adapter";
import { filterAndPickBars } from "@/lib/bar-filters";
import type { ReportDaily, OptimizerOutput, BarItem } from "@/lib/types";
import type { ReportDetail } from "@/lib/fixtures";
import { wpRowsForStatus, type WPStatusFilter } from "@/lib/wp-rows";

type Filter = "all" | "risk" | "caution" | "safe";

const REPORT_SITE_ID = "M15X-Ph3-IBL";

const EMPTY_OPTIMIZER: OptimizerOutput = {
  wp_id: "",
  diagnosis: "",
  similar_cases: [],
  recommendations: [],
  details: [],
};

export default function ReportPage() {
  const [daily, setDaily] = useState<ReportDaily[]>([]);
  const [details, setDetails] = useState<Record<string, ReportDetail>>({});
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [filter, setFilter] = useState<Filter>("all");
  const [selectedWpId, setSelectedWpId] = useState<string | null>(null);
  // 한번 fetch 한 date 는 메모리 캐시 → 좌측 목록에서 다른 날짜 갔다 돌아와도 즉답.
  const detailCacheRef = useRef<Map<string, ReportDetail>>(new Map());

  // 1) list 만 — 32MB jsonb 페이로드 제거. ~50KB.
  useEffect(() => {
    fetch("/api/mock/report")
      .then((r) => r.json())
      .then((d) => {
        setDaily(d.daily);
        // 2026-05-28: URL ?date= 우선 + fallback list[0] (사용자 navigate 의도 보존)
        const urlDate = new URLSearchParams(window.location.search).get("date");
        if (urlDate && /^\d{4}-\d{2}-\d{2}$/.test(urlDate)) {
          setSelectedDate(urlDate);
        } else if (d.daily.length > 0) {
          setSelectedDate(d.daily[0].date);
        }
      });
  }, []);

  // 2) selectedDate 변경 시에만 detail fetch.
  useEffect(() => {
    if (!selectedDate) return;
    const cached = detailCacheRef.current.get(selectedDate);
    if (cached) {
      setDetails((prev) => (prev[selectedDate] ? prev : { ...prev, [selectedDate]: cached }));
      return;
    }
    let cancelled = false;
    fetch(`/api/mock/report/${selectedDate}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: ReportDetail | null) => {
        if (cancelled || !d) return; // 404(해당 일자 daily_report 없음) → 저장 안 함 → !detail empty 상태
        detailCacheRef.current.set(selectedDate, d);
        setDetails((prev) => ({ ...prev, [selectedDate]: d }));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDate]);

  useEffect(() => {
    const detail = details[selectedDate];
    if (!detail) return;
    const wpSummary = (detail.wp_summary as any[]) || [];
    // 1. status='risk' + impact desc
    let initial = wpSummary
      .filter((w: any) => w.status === "risk")
      .sort((a: any, b: any) => (b.impact ?? 0) - (a.impact ?? 0))[0];
    // 2. status='caution' + impact desc
    if (!initial)
      initial = wpSummary
        .filter((w: any) => w.status === "caution")
        .sort((a: any, b: any) => (b.impact ?? 0) - (a.impact ?? 0))[0];
    // 3. wp_summary 의 첫 row
    if (!initial) initial = wpSummary[0];
    // 4. optimizer.default_wp_id fallback
    setSelectedWpId(initial?.wp_id ?? detail.optimizer?.default_wp_id ?? null);
  }, [selectedDate, details]);

  const detail = details[selectedDate];

  // spec 2026-05-21-cpia-ui-4-fixes-design.md §② — daily(530일 desc) 에서 selectedDate -89~0 window 슬라이스.
  const trend90 = useMemo<{ date: string; value: number }[]>(() => {
    if (!selectedDate || daily.length === 0) return [];
    const idx = daily.findIndex((d) => d.date === selectedDate);
    if (idx === -1) return [];
    return daily
      .slice(idx, idx + 90)
      .reverse()
      .map((d) => ({ date: d.date, value: d.productivity_today }));
  }, [selectedDate, daily]);

  // spec §④ — trade_bars 의 필터 결과 (top3+bot7) 와 동일 trade 만 WP 표에 노출.
  const visibleTrades = useMemo(() => {
    if (!detail) return new Set<string>();
    return new Set(filterAndPickBars(detail.trade_bars).map((b) => b.label));
  }, [detail]);

  // 토글 'WP별' 막대 — wp_summary(중복 wp_id 제거) → BarItem. value=생산성, baseline=이력평균.
  const wpBars = useMemo<BarItem[]>(() => {
    const seen = new Set<string>();
    return (detail?.wp_summary ?? [])
      .filter((w) => {
        if (!w.wp_id || seen.has(w.wp_id)) return false;
        seen.add(w.wp_id);
        return true;
      })
      .map((w) => ({
        label: w.wp_name,
        value: w.productivity,
        status: w.status,
        baseline: w.baseline,
      }));
  }, [detail]);

  const diagnosis = useMemo(() => {
    if (!detail) return null;
    const base = diagnose(toDiagnosisInput(detail.kpi, detail.s_curve, REPORT_SITE_ID, detail.scenarios?.site));
    const beP50 = detail.scenarios?.site?.base_p50;
    if (beP50 && typeof beP50.recovery_days === "number") {
      return {
        ...base,
        recovery: {
          p25_days: detail.scenarios?.site?.optimistic_p25?.recovery_days ?? 0,
          p50_days: beP50.recovery_days,
          p75_days: detail.scenarios?.site?.pessimistic_p75?.recovery_days ?? 0,
        },
      };
    }
    return base;
  }, [detail]);

  if (!detail || !diagnosis) {
    return <div className="px-6 py-10 text-ink-light">Loading...</div>;
  }

  // § 3 4분면 필터 → WP 리스트 필터 (safe ↔ normal 매핑)
  const filterToStatus: Record<Filter, WPStatusFilter> = {
    all: "all",
    risk: "risk",
    caution: "caution",
    safe: "normal",
  };
  const wpStatusFilter = filterToStatus[filter];
  // spec §④ — 위 trade bar 매칭된 trade 만 + dead row (impact=0 AND prod=0) 제외.
  // 지연일(delay_days)·AI단축(recovery_days)은 BE(view_builder)가 wp_summary 에 직접 주입 —
  // 지연일=forecasts.delay_days(현황 완료일 슬립), 단축=scenarios.by_wp recovery. FE 파싱 폐기.
  // QuadrantCountKpi 용 — visibleTrades + 활성(impact/productivity>0) 필터.
  const filteredWpRowsBase = detail.wp_summary
    .filter((w) => visibleTrades.has(w.trade) && (w.impact > 0 || w.productivity > 0));
  // WP목록 표 = 전체 wp_summary (status 4분면 필터만). headline Σ(wp_summary) 와 정합.
  const wpListRows = wpRowsForStatus(detail.wp_summary ?? [], wpStatusFilter);
  // 선택 WP — OptimizerResult 진단/만회방안 괄호(지연·AI단축) prop source (wp_summary SSOT).
  const selectedWp = detail.wp_summary.find((w) => w.wp_id === selectedWpId);

  return (
    <div className="flex flex-col">
      <div className="mx-auto w-full max-w-screen-2xl border-b border-border-soft px-6 pt-10 pb-6 md:px-10 md:pt-14">
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          / 04 — Daily Report
        </span>
        <h1 className="mt-3 font-display text-h3 text-ink">
          현장 일일 진단 보고서
        </h1>
        <p className="mt-2 text-body-sm text-ink-mid">
          생산성 분석을 기반으로 한 리스크 검토 및 예측 시나리오를 통해 공사기간 최적화를 제안합니다. 
        </p>
      </div>

      <section className="mx-auto w-full max-w-screen-2xl px-6 pb-20 md:px-10">
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-10">
          <div className="md:col-span-3">
            {/* TopBar(sticky h-16=64px) 아래로 16px 띄워 pin — top-6 이던 시절 상단 잘림 수정.
             * 높이는 pin 위치(5rem)+하단 여백(1.5rem) 만큼 빼서 하단이 뷰포트에서 붕 뜨지 않게. */}
            <div className="flex flex-col overflow-hidden rounded-card border border-border-soft bg-card shadow-xs lg:sticky lg:top-20 lg:h-[calc(100vh-6.5rem)]">
              <ReportDailyList daily={daily} selectedDate={selectedDate} onSelect={setSelectedDate} />
            </div>
          </div>

          <div className="flex flex-col gap-10 md:col-span-7">

            <Section
              eyebrow="/ 01 — 생산성 지표"
              title="현장 생산성 진단"
              subtitle={buildProductivityIssueText(detail)}
            >
              <ProductivityTrendChart
                trend={trend90}
                todayValue={detail.kpi.productivity_today}
                endDate={selectedDate}
              />
              <ProductivityBarToggle
                contractorBars={detail.contractor_bars}
                wpBars={wpBars}
                historyMean={detail.kpi.target_productivity}
                date={selectedDate}
              />
            </Section>

            <Section eyebrow="/ 02 — 4분면 산점도" title="리스크 및 대안 검토">
              {/* 행 높이를 좌측 자연 높이(KPI ~70 + Scatter card ~346 + WP 352 + gaps 24 ≈ 792) 에 맞춰 고정.
                  → 우측 OptimizerResult 가 길어도 컬럼이 늘어나지 않고 내부 스크롤로 처리,
                     좌·우 박스 높이가 일치, 아래 § 03 섹션과 겹치지 않음. (main 데모 레이아웃 보존) */}
              <div className="grid grid-cols-12 items-stretch gap-4 lg:h-[800px]">
                {/* 좌측: 산점도 + 테이블 (세로 stack, WP 테이블은 약 5개 행이 보이도록 고정) */}
                <div className="col-span-12 flex h-full min-h-0 flex-col gap-3 md:col-span-6">
                  {/* QuadrantCountKpi 는 wpSummary prop (병합본 컴포넌트 시그니처) — 필터된 WP 상태 카운트 */}
                  <QuadrantCountKpi wpSummary={filteredWpRowsBase} filter={filter} onFilterChange={setFilter} />
                  <div className="rounded-card border border-border-soft bg-card p-4 shadow-xs">
                    <div className="mb-2 font-display text-base font-semibold text-ink">Impact × Productivity 분포도</div>
                    <QuadrantScatter
                      points={detail.quadrant}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                      filter={filter}
                    />
                  </div>
                  {/* WP 목록 — 약 8개 행 (header 48 + thead 30 + 8 × ~26 ≈ 286, 여유 포함 352) */}
                  <div className="h-[352px] shrink-0">
                    <WPSummaryTable
                      rows={wpListRows}
                      selectedWpId={selectedWpId}
                      onSelect={setSelectedWpId}
                    />
                  </div>
                </div>

                {/* 우측: 진단 결과 (단일 박스, 항목별 구분선). OptimizerResult 가 길어지면 내부 스크롤. */}
                <div className="col-span-12 flex h-full min-h-0 flex-col gap-3 md:col-span-6">
                  <div className="rounded-card border border-border-soft bg-card px-5 py-4 shadow-xs">
                    {(() => {
                      const wpRow = detail.wp_summary.find((w) => w.wp_id === selectedWpId);
                      if (!wpRow) {
                        return (
                          <div className="text-body text-ink-mid">
                            WP 미선택 — 산점도에서 점을 클릭하세요
                          </div>
                        );
                      }
                      const days = wpRow.recovery_days ?? 0;
                      return (
                        <div className="flex items-center justify-between gap-4">
                          <div className="font-display text-h6">
                            <span className="font-semibold text-ink">{wpRow.wp_name}</span>
                            <span className="ml-2 text-ink-light">({wpRow.trade})</span>
                          </div>
                          <div className="flex items-center gap-5">
                            <span className="text-sm text-ink-mid">
                              공기 단축{" "}
                              {days > 0 ? (
                                <span className="font-semibold text-mint-text">-{days}일</span>
                              ) : (
                                <span className="text-ink-light">—</span>
                              )}
                            </span>
                            <span className="inline-flex items-center gap-1.5">
                              <span className={`h-2 w-2 rounded-full ${STATUS_DOT[wpRow.status]}`} />
                              <span className="text-xs font-semibold text-ink-mid">
                                {STATUS_LABEL[wpRow.status]}
                              </span>
                            </span>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                  <div className="flex-1 min-h-0">
                    <OptimizerResult
                      output={
                        detail.optimizer?.by_wp?.[selectedWpId ?? ""]
                        ?? detail.optimizer?.by_wp?.[detail.optimizer?.default_wp_id ?? ""]
                        ?? EMPTY_OPTIMIZER
                      }
                      delayDays={selectedWp?.delay_days}
                      recoveryDays={selectedWp?.recovery_days}
                    />
                  </div>
                </div>
              </div>
            </Section>

            <Section eyebrow="/ 03 — 공정률 추세" title="공기 단축 예측 시나리오">
              <ForecastChart
                diagnosis={diagnosis}
                recoveryActive={selectedWpId !== null}
                delayDays={detail.kpi.delay_days}
                recoveryDays={
                  detail.scenarios?.site?.base_p50?.recovery_days
                  ?? detail.kpi.recovery_days
                }
                scenarios={detail.scenarios?.site}
                reportDate={selectedDate}
                aiSummaryText={detail.site_summary_text}
                aiAdvice={(() => {
                  // wp_summary impact desc top 3 → optimizer.by_wp[wp_id] 의 diagnosis + recommendations 추출.
                  // 룰베이스 fallback (cold_start) 인 wp 는 제외 — LLM 산출 텍스트만.
                  // 2026-05-28: top 3 제한 + impact>0 filter 모두 제거 — advice 있는 모든 wp 표시.
                  // 사용자 의도: site=sum(wp recoveries) 의 산출 근거 추적 가능 (impact=0 도 recovery_days 합산).
                  // wp_summary 중복 row dedup — 같은 wp_id 첫 번째만.
                  const seen = new Set<string>();
                  const top = [...(detail.wp_summary ?? [])]
                    .filter((w) => {
                      if (!w.wp_id || seen.has(w.wp_id)) return false;
                      seen.add(w.wp_id);
                      return true;
                    })
                    .sort((a, b) => (b.impact ?? 0) - (a.impact ?? 0));
                  const by_wp = detail.optimizer?.by_wp ?? {};
                  const wpScenarios = (detail.scenarios as any)?.by_wp ?? {};
                  return top
                    .map((w) => {
                      const o = by_wp[w.wp_id];
                      if (!o) return null;
                      // 2026-05-27 Task 22 후속: V10 schema (keyword/action/reason) 인식.
                      // 옛 string + 옛 {text} + V10 {keyword, action, reason} 셋 다 합성.
                      // 2026-05-29 (2차): 개조식 — [키워드] 조치 한 줄 (이유는 §02 상세 카드에서, 여기선 간결).
                      const recs = (o.recommendations ?? []).map((r: any) => {
                        if (typeof r === "string") return r;
                        if (r.text) return r.text;
                        if (r.keyword && r.action) {
                          return `[${r.keyword}] ${r.action}`;
                        }
                        return "";
                      }).filter(Boolean);
                      const dg = o.diagnosis && o.diagnosis !== "cold_start" ? o.diagnosis : undefined;
                      if (recs.length === 0 && !dg) return null;
                      const wpScen = wpScenarios[w.wp_id];
                      const wpRecoveryDays = wpScen?.base_p50?.recovery_days;
                      return {
                        wp_name: w.wp_name,
                        trade: w.trade,
                        recovery_days: typeof wpRecoveryDays === "number" ? wpRecoveryDays : undefined,
                        diagnosis: dg,
                        recommendations: recs,
                      };
                    })
                    .filter((x): x is NonNullable<typeof x> => x !== null);
                })()}
              />
            </Section>

          </div>
        </div>
      </section>
    </div>
  );
}

/** 압축 조건 태그 → 표시용(띄어쓰기). */
const CAUSE_LABEL: Record<string, string> = {
  자재미입고: "자재 미입고",
  인력부족: "인력 부족",
  사양변경: "사양 변경",
  병행작업: "병행작업",
};

/** optimizer WP 출력에서 오늘의 원인(조건) 추출 — diagnosis 선두 "○○ 조건 ·",
 *  없으면 similar_cases 최빈 비-정상 condition. 원인 못 찾으면 null. */
function extractWpCause(o: any): string | null {
  const dg = String(o?.diagnosis ?? "");
  let c = dg.includes("조건") ? dg.split("조건")[0].trim() : "";
  if (!c || c === "정상") {
    const conds: string[] = (o?.similar_cases ?? [])
      .map((x: any) => x?.condition)
      .filter((x: any) => x && x !== "정상");
    c =
      conds.sort(
        (a, b) => conds.filter((v) => v === b).length - conds.filter((v) => v === a).length,
      )[0] ?? "";
  }
  if (!c || c === "정상") return null;
  return CAUSE_LABEL[c] ?? c;
}

function fmtPct(v: number): string {
  return (Math.round(v * 10) / 10).toString();
}

/**
 * 현장 생산성 진단 2줄 (맥락 인식형). 날짜별 데이터로 자동 생성.
 * 1줄: 사이트 전체 성과 — 이력 평균 대비 잘하는 날/저조한 날 규정.
 * 2줄: 저조 공종(담당 업체 N%, 원인)을 짚되,
 *   - 잘하는 날 → "개선하면 더 끌어올릴 수 있다" (기회 프레이밍)
 *   - 저조한 날 → "보완하면 약 N일 내 만회 가능" (회복 프레이밍, recovery_days)
 * 원인을 가진 저조 공종이 없으면 전체 흐름만으로 마무리.
 */
function buildProductivityIssueText(detail: ReportDetail): string {
  const kpi = detail.kpi;
  const trades = detail.trade_bars ?? [];
  // 저조 공종 후보: risk 우선, 없으면 목표 미달 중 최저 — 생산성 오름차순.
  let worst = [...trades].filter((t) => t.status === "risk").sort((a, b) => a.value - b.value);
  if (worst.length === 0) {
    const tgt = kpi.target_productivity ?? 100;
    worst = [...trades].filter((t) => t.value < tgt).sort((a, b) => a.value - b.value);
  }
  const byWp = detail.optimizer?.by_wp ?? {};
  const seen = new Set<string>();
  const wpRows = (detail.wp_summary ?? []).filter((w) => {
    if (!w.wp_id || seen.has(w.wp_id)) return false;
    seen.add(w.wp_id);
    return true;
  });

  // 공종별: 해당 공종 WP 중 생산성 최저 + 원인 추출 가능한 것 → {공종, 업체, 공종값, 원인}.
  const parts: { trade: string; bp: string; value: number; cause: string }[] = [];
  for (const t of worst) {
    if (parts.length >= 2) break;
    if (parts.some((p) => p.trade === t.label)) continue;
    const cand = wpRows
      .filter((w) => w.trade === t.label)
      .sort((a, b) => a.productivity - b.productivity);
    for (const w of cand) {
      const cause = extractWpCause(byWp[w.wp_id]);
      if (cause) {
        parts.push({ trade: t.label, bp: w.bp_name, value: t.value, cause });
        break;
      }
    }
  }

  // 전체 성과 리드 — 오늘 사이트 생산성이 이력 평균을 웃돌면 '잘하는 날',
  // 밑돌면 '저조한 날' 로 규정해 2줄째 톤(개선 기회 vs 만회)을 가른다.
  const today = kpi.productivity_today;
  const target = kpi.target_productivity ?? 100;
  const gap = today - target;
  const good = gap >= 0;
  const line1 = good
    ? gap > 0
      ? `현재 현장 생산성은 ${fmtPct(today)}%로 목표 생산성(${fmtPct(target)}%)을 ${fmtPct(gap)}%p 웃도는 양호한 흐름입니다.`
      : `현재 현장 생산성은 ${fmtPct(today)}%로 목표 생산성(${fmtPct(target)}%)과 동일한 안정적 수준입니다.`
    : `현재 현장 생산성은 ${fmtPct(today)}%로 목표 생산성(${fmtPct(target)}%) 대비 ${fmtPct(Math.abs(gap))}%p 낮은 상황입니다.`;

  // 저조 공종을 못 찾으면 전체 흐름만으로 마무리.
  if (parts.length === 0) {
    const line2 = good
      ? `전 공종이 고르게 진행되고 있어, 현 흐름을 유지하면 계획을 앞당길 여지가 있습니다.`
      : `현 추세가 이어지면 준공 지연이 우려되어 공종별 점검이 필요합니다.`;
    return `${line1}\n${line2}`;
  }

  // 공종 이슈 — 잘하는 날: 개선 기회 / 저조한 날: 만회 방향.
  const issues = parts
    .map((p) => `${p.trade}(${p.bp} ${fmtPct(p.value)}%, ${p.cause})`)
    .join("·");
  const recovery = Math.round(kpi.recovery_days ?? 0);
  const line2 = good
    ? `다만 ${issues} 등이 평균을 밑돌고 있어 개선이 필요합니다.`
    : `특히 ${issues} 등이 생산성을 끌어내리고 있어, 우선 보완하면 ${recovery > 0 ? `약 ${recovery}일 내 ` : ""}만회가 가능합니다.`;
  return `${line1}\n${line2}`;
}

function Section({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
          {eyebrow}
        </span>
        <h2 className="mt-1 font-display text-h5 text-ink">{title}</h2>
        {subtitle && (
          <p className="mt-2 whitespace-pre-line text-body-sm font-light text-ink-mid">{subtitle}</p>
        )}
      </div>
      {children}
    </section>
  );
}

