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
  CartesianGrid,
} from "recharts";
import { cn } from "@/lib/utils";
import type { ProductivityDiagnosis } from "@/lib/types";
import { ConfidenceBadge } from "../reports/ConfidenceBadge";

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

  return (
    <div className="rounded-card border border-border-soft bg-card p-5 shadow-xs">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div className="font-display text-base font-semibold text-ink">
          공정률 추세 예측
        </div>
        <ConfidenceBadge sampleSize={diagnosis.sample_size} />
      </div>

      <div className="mb-4 grid grid-cols-2 gap-x-8">
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
              일 {recoveryDays > 0 ? "추가 단축 가능" : "추가 단축 불가"}
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

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 0 }}>
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

          {/* Plan — 가장 강조 (회색 두꺼운 실선) */}
          <Line dataKey="planned" stroke="#4b5563" strokeWidth={2.5} dot={false} isAnimationActive={false} />

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
        </ComposedChart>
      </ResponsiveContainer>

      <div className="mt-4 space-y-1.5 rounded-md bg-surface-soft/50 px-3 py-2.5 text-sm leading-relaxed text-ink-mid">
        <p>📊 {situationNarrative(diagnosis, delayDays)}</p>
        <p>⚡ {outlookNarrative(diagnosis, delayDays, recoveryDays)}</p>
      </div>
    </div>
  );
}

/** 현재 상황 분석 — 이력 평균 대비 위치 + 추세 + 현 공기 지연/단축 결론. */
function situationNarrative(d: ProductivityDiagnosis, delayDays: number): string {
  const absZ = Math.abs(d.z_score).toFixed(1);
  const direction = d.z_score >= 0 ? "위" : "아래";
  const within = Math.abs(d.z_score) < 1.5;
  const rangeText = within
    ? `이력 평균보다 ${absZ}σ ${direction}쪽 정상 변동 범위 안에 머물고 있지만`
    : `이력 평균보다 ${absZ}σ ${direction}쪽 정상 범위를 벗어난 구간이며`;
  const trendText =
    delayDays > 0
      ? `최근 30일 동안 생산성이 우하향해 현 추세 유지 시 계획 대비 ${delayDays}일 지연이 예상됩니다.`
      : delayDays < 0
        ? `최근 추세가 우상향해 현 추세 유지 시 계획 대비 ${Math.abs(delayDays)}일 단축이 가능합니다.`
        : `현재 추세는 계획선과 거의 일치합니다.`;
  return `${rangeText}, ${trendText}`;
}

/** 만회 전망 — AI 권고 적용 시 단축 효과 + 최종 공기 결론. */
function outlookNarrative(
  d: ProductivityDiagnosis,
  delayDays: number,
  recoveryDays: number,
): string {
  if (recoveryDays <= 0) {
    return `자연 회귀만으로는 추가 회복이 어렵고, AI 권고로도 의미 있는 단축은 어려운 상태입니다.`;
  }
  const remaining = delayDays - recoveryDays;
  if (remaining > 0) {
    return `AI 권고 적용 시 ${recoveryDays}일 단축이 가능하며, 만회 시나리오를 따르면 계획 공기 대비 ${remaining}일 차이까지 좁힐 수 있습니다.`;
  }
  if (remaining === 0) {
    return `AI 권고 적용 시 ${recoveryDays}일 단축으로 계획 공기 회복이 가능합니다.`;
  }
  return `AI 권고 적용 시 ${recoveryDays}일 단축으로 계획 공기를 ${Math.abs(remaining)}일 앞당길 수 있습니다.`;
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
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-mono uppercase tracking-wider transition-colors",
        active
          ? "border-brand bg-brand-light text-brand-text"
          : "border-border bg-card text-ink-light hover:border-ink-light/40 hover:text-ink-mid",
        forced && "cursor-default opacity-90",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />
      {label}
      {forced && <span className="ml-0.5 text-[9px]">●</span>}
    </button>
  );
}
