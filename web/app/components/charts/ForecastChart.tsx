"use client";
import { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceDot,
  ReferenceLine,
  Label,
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";
import type { ProductivityDiagnosis } from "@/lib/types";
import type { ScenarioSet } from "@/lib/fixtures";

interface Props {
  diagnosis: ProductivityDiagnosis;
  /** Optimizer 권고 시나리오를 강조 표시. § 4 에서 WP 선택 시 true. */
  recoveryActive?: boolean;
  /** 현 추세 공기 차이 (양수 = 지연, 음수 = 앞서감). */
  delayDays: number;
  /** 최적화 적용 시 단축 가능 일수 (양수). */
  recoveryDays: number;
  /** BE 산출 site 시나리오 — 추적성 메타 + 3 시나리오 비교 표용. */
  scenarios?: Partial<ScenarioSet>;
  /** 기준일 (selectedDate, 메타 표시용). */
  reportDate?: string;
  /** LLM 산출 — 공기 단축 가능한 공종 + 권고사항 (Optimizer agent). 룰베이스 narrative 대체. */
  aiAdvice?: Array<{
    wp_name: string;
    trade: string;
    recovery_days?: number;
    diagnosis?: string;
    recommendations: string[];
  }>;
  /** BE Optimizer LLM 산출 — site 수준 1~2단락 진척 요약. 룰베이스 narrative 대체. */
  aiSummaryText?: string | null;
}

interface ToggleState {
  optimistic: boolean;     // 만회 시나리오 (AI catch-up)
  noaction: boolean;       // 현 추세 연장 — BE forecast 선 (격차 유지)
}

export function ForecastChart({
  diagnosis,
  recoveryActive = false,
  delayDays,
  recoveryDays,
  scenarios,
  reportDate,
  aiAdvice,
  aiSummaryText,
}: Props) {
  // default on — 3선 동시 비교가 기본. 사용자가 끄고 싶을 때만 끔.
  const [toggles, setToggles] = useState<ToggleState>({
    optimistic: true,
    noaction: true,
  });

  const showOptimistic = toggles.optimistic || recoveryActive;

  // X 축 범위 — 720일 그대로면 마지막 1~2주가 압축돼 spike 처럼 보임.
  // 기준일(today=lastActual) 기준 -90일 ~ +200일 (시나리오 ec 가 +180일 근처라 200일로 여유).
  const allData = diagnosis.s_curve.map((p, i) => ({
    date: p.date,
    planned: p.planned,
    actual: p.actual,
    forecast: (p as any).forecast,  // BE _extend_forecast 산출 — 현 추세 연장 (격차 유지)
    band_low:  diagnosis.band_p25[i],
    band_high: diagnosis.band_p75[i],
    base:      diagnosis.scenarios.base.curve[i],
    optimistic:  diagnosis.scenarios.optimistic.curve[i],
  }));
  // todayIdx = actual 마지막 점 (역순 탐색 — sparse hole 회피)
  let todayIdx = -1;
  for (let i = allData.length - 1; i >= 0; i--) {
    if (allData[i].actual !== undefined && allData[i].actual !== null) { todayIdx = i; break; }
  }
  if (todayIdx < 0) todayIdx = allData.length - 1;
  const windowStart = Math.max(0, todayIdx - 90);
  const windowEnd   = Math.min(allData.length, todayIdx + 240);
  const data = allData.slice(windowStart, windowEnd);

  const firstUndef = data.findIndex((d) => d.actual === undefined);
  const lastIdx = firstUndef === -1 ? data.length - 1 : firstUndef - 1;
  const lastPoint = lastIdx >= 0 ? data[lastIdx] : null;

  // ReferenceDot 마커 — BE 산출 ec 직접 사용 (FE 차트 좌표와 일치).
  // planned 100% 도달은 s_curve 안에서 찾고, 시나리오들은 scenarios prop 에서 가져옴.
  const planEnd = (() => {
    for (const d of data) {
      if (typeof d.planned === "number" && d.planned >= 100) return d.date;
    }
    return null;
  })();
  const noActionEnd = scenarios?.no_action?.expected_completion ?? null;
  // catch-up intersection 마커 — FE 산출 (recoveryDays 만에 plan 따라잡는 점)
  const baseCatchUp = diagnosis.scenarios.base.catch_up;
  const optCatchUp = diagnosis.scenarios.optimistic.catch_up;

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="mb-3 font-display text-base font-semibold text-ink">
        공정률 추세 예측
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-x-10 gap-y-3">
        <div>
          <div className="text-sm text-ink-mid">예상 공기</div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {delayDays > 0 ? "D+" : delayDays < 0 ? "D−" : ""}{Math.abs(delayDays)}
            </span>
            <span className="text-base text-ink-mid">
              일 {delayDays > 0 ? "지연 예상" : delayDays < 0 ? "단축 예상" : "계획 동일"}
            </span>
          </div>
        </div>
        <div>
          <div className="text-sm text-ink-mid">최적화 공기</div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="font-display text-h3 font-semibold tracking-[-0.015em] text-ink">
              {recoveryDays > 0 ? "-" : ""}{recoveryDays}
            </span>
            <span className="text-base text-ink-mid">
              일 {recoveryDays > 0 ? "단축 가능" : "단축 불가"}
            </span>
          </div>
        </div>

        {/* 추적성 메타 — 산출 근거 한눈에 */}
        {(scenarios || reportDate) && (
          <dl className="ml-auto grid grid-cols-[auto_auto] gap-x-4 gap-y-1.5 rounded-md bg-surface-soft/50 px-4 py-2.5 text-xs leading-tight">
            {reportDate && (
              <div className="contents">
                <dt className="text-ink-light">기준일</dt>
                <dd className="font-mono text-ink-mid">{reportDate}</dd>
              </div>
            )}
            {planEnd && (
              <div className="contents">
                <dt className="text-ink-light">계획 완공</dt>
                <dd className="font-mono text-ink-mid">{planEnd}</dd>
              </div>
            )}
            {scenarios?.no_action?.expected_completion && (
              <div className="contents">
                <dt className="text-ink-light">현황 (예측)</dt>
                <dd className="font-mono" style={{ color: "#ef4444" }}>
                  {scenarios.no_action.expected_completion}
                  {delayDays > 0 && (
                    <span className="ml-1 text-[10px] font-semibold">(D+{delayDays})</span>
                  )}
                </dd>
              </div>
            )}
            {scenarios?.base_p50?.recovery_days != null && (
              <div className="contents">
                <dt className="text-ink-light">AI 시나리오</dt>
                <dd className="font-mono text-mint-text">
                  {scenarios.base_p50.recovery_days}일 만에 따라잡음
                </dd>
              </div>
            )}
          </dl>
        )}
      </div>

      {/* 범례 — 의미 한눈에 (토글 없이 항상 표시) */}
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12px] text-ink-mid">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 bg-ink" />
          현황 (실적)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: "#ef4444" }} />
          현황 (예측)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4" style={{ background: "#94a3b8" }} />
          플랜 (계획)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: "#0ea76a" }} />
          AI 시나리오
        </span>
      </div>

      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={data} margin={{ top: 28, right: 24, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#eef0f4" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#7a8494" }}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            labelFormatter={(v) => String(v)}
          />

          <Area dataKey="band_high" stroke="none" fill="#e8eeff" fillOpacity={0.4} activeDot={false} isAnimationActive={false} />
          <Area dataKey="band_low"  stroke="none" fill="#ffffff" fillOpacity={1}   activeDot={false} isAnimationActive={false} />

          {/* 플랜 (계획) — 회색 실선 */}
          <Line dataKey="planned" stroke="#94a3b8" strokeWidth={2} dot={false} isAnimationActive={false} />

          {/* 현황 (실적) — 검정 굵은 실선 */}
          <Line dataKey="actual" stroke="#0d1117" strokeWidth={3} dot={false} isAnimationActive={false} />

          {/* 현황 (예측) — 빨강 dashed (BE forecast — actual trend 연장, plan 과 평행 격차 유지) */}
          <Line dataKey="forecast" stroke="#ef4444" strokeWidth={2} strokeDasharray="6 5" dot={false} isAnimationActive={false} connectNulls={false} />

          {/* AI 시나리오 — mint 점선. catch-up + plan 동행 (catch-up 까지만 라인 그림). */}
          <Line dataKey="base" stroke="#0ea76a" strokeWidth={2.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} connectNulls={false} />

          {lastPoint && lastPoint.actual !== undefined && (
            <ReferenceDot
              x={lastPoint.date}
              y={lastPoint.actual}
              r={5}
              fill="#0d1117"
              stroke="#0ea76a"
              strokeWidth={2}
            />
          )}

          {/* 100% 완료선 (가로 점선) */}
          <ReferenceLine y={100} stroke="#cbd5e1" strokeDasharray="3 3" />

          {/* 계획 완공 — 회색 마커 (위쪽) */}
          {planEnd && (
            <ReferenceDot x={planEnd} y={100} r={5} fill="#94a3b8" stroke="#ffffff" strokeWidth={2}>
              <Label
                value={`계획 ${planEnd.slice(5)}`}
                position="top"
                offset={14}
                fill="#475569"
                fontSize={11}
                fontWeight={600}
              />
            </ReferenceDot>
          )}

          {/* 현황 (예측) 완공 — 빨강 마커 (아래쪽 — 계획 옆에 평행 배치, D+N 강조) */}
          {noActionEnd && (
            <ReferenceDot x={noActionEnd} y={100} r={5} fill="#ef4444" stroke="#ffffff" strokeWidth={2}>
              <Label
                value={
                  (delayDays > 0
                    ? `현황 D+${delayDays}`
                    : delayDays < 0
                    ? `현황 D−${Math.abs(delayDays)}`
                    : "현황 계획 동일") + ` · ${noActionEnd.slice(5)}`
                }
                position="bottom"
                offset={14}
                fill="#ef4444"
                fontSize={11}
                fontWeight={700}
              />
            </ReferenceDot>
          )}

          {/* AI 시나리오 catch-up intersection — mint 마커. plan 따라잡는 시점 */}
          {baseCatchUp && (
            <ReferenceDot
              x={baseCatchUp.date}
              y={baseCatchUp.percent}
              r={5}
              fill="#0ea76a"
              stroke="#ffffff"
              strokeWidth={2}
            >
              <Label
                value={`AI 시나리오 ${baseCatchUp.date.slice(5)}`}
                position="top"
                offset={14}
                fill="#0ea76a"
                fontSize={11}
                fontWeight={700}
              />
            </ReferenceDot>
          )}

        </ComposedChart>
      </ResponsiveContainer>

      {/* 3선 요약 — 현황 / 플랜 / AI 시나리오 */}
      {scenarios && (
        <div className="mt-4 overflow-hidden rounded-md border border-border-soft">
          <table className="w-full text-sm">
            <thead className="bg-surface-soft/50 text-[11px] uppercase tracking-wider text-ink-light">
              <tr>
                <th className="px-3 py-2 text-left font-semibold">구분</th>
                <th className="px-3 py-2 text-right font-semibold">상태</th>
                <th className="px-3 py-2 text-right font-semibold">완공 예정일</th>
              </tr>
            </thead>
            <tbody>
              {/* 현황 — 오늘까지 실적 + 추세 연장 */}
              <tr className="border-t border-border-soft">
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#ef4444" }} />
                    <span className="text-ink-mid">현황</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-ink-mid">
                  {reportDate ?? "—"} 기준 추세 연장
                </td>
                <td className="px-3 py-2 text-right">
                  {scenarios.no_action?.expected_completion ? (
                    <>
                      <span className="font-mono" style={{ color: "#ef4444" }}>
                        {scenarios.no_action.expected_completion}
                      </span>
                      {delayDays > 0 && (
                        <span className="ml-1 text-[11px] font-semibold" style={{ color: "#ef4444" }}>
                          (D+{delayDays})
                        </span>
                      )}
                    </>
                  ) : "—"}
                </td>
              </tr>
              {/* 플랜 — 계획 완공일 */}
              <tr className="border-t border-border-soft">
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#94a3b8" }} />
                    <span className="text-ink-mid">플랜</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-ink-mid">당초 계획</td>
                <td className="px-3 py-2 text-right font-mono text-ink">{planEnd ?? "—"}</td>
              </tr>
              {/* AI 시나리오 — catch-up 후 plan 동행 */}
              <tr className="border-t border-border-soft bg-surface-soft/30">
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#0ea76a" }} />
                    <span className="font-semibold text-ink">AI 시나리오</span>
                  </span>
                </td>
                <td className="px-3 py-2 text-right text-ink">
                  {scenarios.base_p50?.recovery_days
                    ? <>
                        <span className="font-semibold text-mint-text">
                          {scenarios.base_p50.recovery_days}일
                        </span>
                        <span className="text-ink-mid"> 만에 plan 따라잡음</span>
                      </>
                    : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <span className="font-mono text-ink">{planEnd ?? "—"}</span>
                  <span className="ml-1 text-[11px] text-ink-light">(계획 동일)</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 space-y-3 rounded-md bg-surface-soft/50 px-4 py-3 text-sm leading-relaxed">
        {/* 현황 요약 — Optimizer LLM 산출 (BE site_summary_text). 없으면 룰베이스 fallback. */}
        <div className="text-ink-mid">
          {aiSummaryText ? (
            <p>{aiSummaryText}</p>
          ) : (
            <>
              <p>{situationNarrative(delayDays)}</p>
              <p>{outlookNarrative(delayDays, recoveryDays)}</p>
            </>
          )}
        </div>

        {/* LLM 산출 권고사항 — 공기 단축 가능한 공종 + 조치 (Optimizer agent) */}
        {aiAdvice && aiAdvice.length > 0 ? (
          <div className="border-t border-border-soft pt-3">
            <div className="mb-2 inline-flex items-center gap-1.5 text-[12px] font-semibold text-mint-text">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: "#0ea76a" }} />
              AI 권고 — 공기 단축 가능한 공종
            </div>
            <ul className="space-y-2.5 text-sm text-ink">
              {aiAdvice.map((wp, idx) => (
                <li key={idx} className="rounded bg-card px-3 py-2 ring-1 ring-border-soft">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="text-[12px] font-semibold text-ink">
                        {wp.wp_name}
                        <span className="ml-1.5 font-normal text-ink-light">({wp.trade})</span>
                      </div>
                      {wp.diagnosis && (
                        <p className="mt-1 text-[12.5px] text-ink-mid">{wp.diagnosis}</p>
                      )}
                      {wp.recommendations.length > 0 && (
                        <ul className="mt-1.5 ml-3 list-disc space-y-0.5 text-[12.5px] text-ink-mid">
                          {wp.recommendations.slice(0, 2).map((r, ri) => (
                            <li key={ri}>{r}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                    {typeof wp.recovery_days === "number" && (
                      <span className="shrink-0 text-[16px] font-bold text-mint-text">
                        {wp.recovery_days > 0 ? `−${wp.recovery_days}일 만회` : "0일 만회"}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {scenarios && typeof scenarios.base_p50?.case_count === "number" && (
              <p className="mt-2 text-[11px] text-ink-light">
                * 권고는 과거 유사 상황 <b>{scenarios.base_p50.case_count}건</b> 의 회복 패턴
                기반 LLM 산출. 적용 시 약 <b>{recoveryDays}일</b> 만에 plan 따라잡을 수 있습니다.
              </p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface ScenarioRowProps {
  label: string;
  dot: string;
  days: number | undefined;
  daysLabel?: string;  // 기본: "일 후"
  date: string | null;
  suffix: string;
  caseCount: number | undefined;
  emphasized?: boolean;
}

function ScenarioRow({ label, dot, days, daysLabel, date, suffix, caseCount, emphasized }: ScenarioRowProps) {
  const tone = emphasized ? "text-ink font-semibold" : "text-ink-mid";
  return (
    <tr className={cn("border-t border-border-soft", emphasized && "bg-surface-soft/30")}>
      <td className="px-3 py-2">
        <span className="inline-flex items-center gap-2">
          <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
          <span className={tone}>{label}</span>
        </span>
      </td>
      <td className="px-3 py-2 text-right font-mono text-ink">
        {typeof days === "number" ? `${days}일 ${daysLabel ?? "후"}` : "—"}
      </td>
      <td className="px-3 py-2 text-right text-ink-mid">
        {date ? (
          <>
            <span className="font-mono text-ink">{date}</span>
            <span className="ml-1 text-[11px] text-ink-light">{suffix}</span>
          </>
        ) : "—"}
      </td>
      <td className="px-3 py-2 text-right text-ink-light">
        {typeof caseCount === "number" ? `${caseCount}건` : "—"}
      </td>
    </tr>
  );
}

/** 현재 상황 — S-curve(누적 진척률) 의미에 맞춘 경영진 자연어. */
function situationNarrative(delayDays: number): string {
  if (delayDays > 0) {
    return `지금까지의 진척률이 당초 계획보다 뒤처져 있고, 그 격차도 점점 벌어지고 있습니다. 지금 페이스가 이어지면 당초 계획보다 ${delayDays}일 늦게 완공될 것으로 보입니다.`;
  }
  if (delayDays < 0) {
    return `지금까지의 진척률이 당초 계획보다 앞서 있고, 흐름도 양호하게 유지되고 있습니다. 이대로라면 당초 계획보다 ${Math.abs(delayDays)}일 빨리 완공할 수 있습니다.`;
  }
  return `현재 진척률은 당초 계획과 거의 일치하게 진행되고 있습니다.`;
}

/** 만회 전망 — AI 권고 효과를 경영진 의사결정 언어로. */
function outlookNarrative(delayDays: number, recoveryDays: number): string {
  if (recoveryDays <= 0) {
    return `현재로서는 AI 가 제안할 수 있는 만회 방안이 제한적이며, 일정 회복은 어려운 상황입니다.`;
  }
  const remaining = delayDays - recoveryDays;
  if (remaining > 0) {
    return `AI 가 제안하는 조치를 시행하면 ${recoveryDays}일을 만회할 수 있어, 최종 공기는 당초 계획보다 ${remaining}일 늦어지는 선에서 마무리할 수 있습니다.`;
  }
  if (remaining === 0) {
    return `AI 가 제안하는 조치를 시행하면 ${recoveryDays}일을 만회할 수 있어, 당초 계획대로 공기를 회복할 수 있습니다.`;
  }
  return `AI 가 제안하는 조치를 시행하면 ${recoveryDays}일을 만회할 수 있어, 당초 계획보다 ${Math.abs(remaining)}일 빨리 완공할 수 있습니다.`;
}

interface ToggleChipProps {
  label: string;
  color: "mint" | "rose" | "ink";
  active: boolean;
  forced?: boolean;
  onClick: () => void;
}

function ToggleChip({ label, color, active, forced, onClick }: ToggleChipProps) {
  const dot = {
    mint: "bg-mint",
    rose: "bg-rose",
    ink:  "bg-ink-mid",
  }[color];
  return (
    <button
      type="button"
      onClick={forced ? undefined : onClick}
      disabled={forced}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold transition-colors",
        active
          ? "border-brand bg-brand-light text-brand-text"
          : "border-border bg-card text-ink-light hover:border-ink-light/40 hover:text-ink-mid",
        forced && "cursor-default opacity-90",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
      {label}
      {forced && <span className="ml-0.5 text-[10px]">●</span>}
    </button>
  );
}
