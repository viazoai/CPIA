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
interface Props {
  diagnosis: ProductivityDiagnosis;
  /** Optimizer 권고 시나리오를 강조 표시. § 4 에서 WP 선택 시 true. */
  recoveryActive?: boolean;
  /** 현 추세 공기 차이 (양수 = 지연, 음수 = 앞서감). */
  delayDays: number;
  /** 최적화 적용 시 단축 가능 일수 (양수). */
  recoveryDays: number;
}

interface ToggleState {
  optimistic: boolean;
  pessimistic: boolean;
}

export function ForecastChart({ diagnosis, recoveryActive = false, delayDays, recoveryDays }: Props) {
  const [toggles, setToggles] = useState<ToggleState>({
    optimistic: false,
    pessimistic: false,
  });

  const showOptimistic = toggles.optimistic || recoveryActive;

  const data = diagnosis.s_curve.map((p, i) => ({
    date: p.date,
    planned: p.planned,
    actual: p.actual,
    band_low:  diagnosis.band_p25[i],
    band_high: diagnosis.band_p75[i],
    base:      diagnosis.scenarios.base.curve[i],
    optimistic:  diagnosis.scenarios.optimistic.curve[i],
    pessimistic: diagnosis.scenarios.pessimistic.curve[i],
  }));

  const firstUndef = data.findIndex((d) => d.actual === undefined);
  const lastIdx = firstUndef === -1 ? data.length - 1 : firstUndef - 1;
  const lastPoint = lastIdx >= 0 ? data[lastIdx] : null;

  // 100% 도달 시점 찾기 — 각 시나리오가 어디서 끝나는지 시각화
  const completionDate = (key: "planned" | "base" | "optimistic"): string | null => {
    for (const d of data) {
      const v = d[key] as number | null | undefined;
      if (typeof v === "number" && v >= 100) return d.date;
    }
    return null;
  };
  const planEnd = completionDate("planned");
  const baseEnd = completionDate("base");
  const optEnd  = completionDate("optimistic");

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="mb-3 font-display text-base font-semibold text-ink">
        공정률 추세 예측
      </div>

      <div className="mb-4 flex flex-wrap gap-x-10">
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
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        <ToggleChip
          label="만회 시나리오"
          color="mint"
          active={showOptimistic}
          forced={recoveryActive}
          onClick={() => setToggles((s) => ({ ...s, optimistic: !s.optimistic }))}
        />
        <ToggleChip
          label="현 추세 유지"
          color="rose"
          active={toggles.pessimistic}
          onClick={() => setToggles((s) => ({ ...s, pessimistic: !s.pessimistic }))}
        />
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

          {/* Plan — 보조선 (옅은 회색 실선) */}
          <Line dataKey="planned" stroke="#94a3b8" strokeWidth={2} dot={false} isAnimationActive={false} />

          {/* Actual — 가장 강조 (검정 더 두꺼운 실선) */}
          <Line dataKey="actual" stroke="#0d1117" strokeWidth={3} dot={false} isAnimationActive={false} />

          {/* Forecast (base) — 오늘부터 시작, 점선으로 미래 예측임을 표시 */}
          <Line dataKey="base" stroke="#1a56db" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} connectNulls={false} />

          {showOptimistic && (
            <Line dataKey="optimistic" stroke="#0ea76a" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} connectNulls={false} />
          )}

          {toggles.pessimistic && (
            <Line dataKey="pessimistic" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} connectNulls={false} />
          )}

          {lastPoint && lastPoint.actual !== undefined && (
            <ReferenceDot
              x={lastPoint.date}
              y={lastPoint.actual}
              r={5}
              fill="#0d1117"
              stroke="#1a56db"
              strokeWidth={2}
            />
          )}

          {/* 100% 완료선 (가로 점선) */}
          <ReferenceLine y={100} stroke="#cbd5e1" strokeDasharray="3 3" />

          {/* 계획 완공 시점 — 위쪽 라벨 */}
          {planEnd && (
            <ReferenceDot x={planEnd} y={100} r={5} fill="#94a3b8" stroke="#ffffff" strokeWidth={2}>
              <Label value="계획" position="top" offset={10} fill="#475569" fontSize={11} fontWeight={600} />
            </ReferenceDot>
          )}

          {/* 현 추세 도달 시점 — 아래쪽 라벨 (겹침 방지) */}
          {baseEnd && (
            <ReferenceDot x={baseEnd} y={100} r={5} fill="#1a56db" stroke="#ffffff" strokeWidth={2}>
              <Label
                value={delayDays > 0 ? `D+${delayDays}` : delayDays < 0 ? `D−${Math.abs(delayDays)}` : "동일"}
                position="bottom"
                offset={10}
                fill="#1a56db"
                fontSize={11}
                fontWeight={700}
              />
            </ReferenceDot>
          )}

          {/* 최적화 도달 시점 — 위쪽 라벨 */}
          {showOptimistic && optEnd && (
            <ReferenceDot x={optEnd} y={100} r={5} fill="#0ea76a" stroke="#ffffff" strokeWidth={2}>
              <Label
                value={recoveryDays > 0 ? `−${recoveryDays}일` : "최적화"}
                position="top"
                offset={10}
                fill="#0ea76a"
                fontSize={11}
                fontWeight={700}
              />
            </ReferenceDot>
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-4 space-y-1.5 rounded-md bg-surface-soft/50 px-3 py-2.5 text-sm leading-relaxed text-ink-mid">
        <p>{situationNarrative(diagnosis, delayDays)}</p>
        <p>{outlookNarrative(diagnosis, delayDays, recoveryDays)}</p>
      </div>
    </div>
  );
}

/** 현재 상황 — 경영진 친화적 자연어 (통계 용어 회피). */
function situationNarrative(d: ProductivityDiagnosis, delayDays: number): string {
  const within = Math.abs(d.z_score) < 1.5;
  const direction = d.z_score >= 0 ? "높은" : "낮은";
  const rangeText = within
    ? `현재 생산성은 예년 평균과 비슷한 수준입니다.`
    : `현재 생산성이 예년 평균을 크게 벗어난 ${direction} 상태입니다.`;
  const trendText =
    delayDays > 0
      ? `다만 최근 한 달간 생산성이 점차 떨어지는 추세로, 지금 흐름이 이어지면 당초 계획보다 ${delayDays}일 늦게 완공될 것으로 보입니다.`
      : delayDays < 0
        ? `최근 흐름이 좋아지고 있어, 이대로 유지된다면 당초 계획보다 ${Math.abs(delayDays)}일 빨리 완공할 수 있습니다.`
        : `현재 추세는 당초 계획과 거의 일치합니다.`;
  return `${rangeText} ${trendText}`;
}

/** 만회 전망 — AI 권고 효과를 경영진 의사결정 언어로. */
function outlookNarrative(
  _d: ProductivityDiagnosis,
  delayDays: number,
  recoveryDays: number,
): string {
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
