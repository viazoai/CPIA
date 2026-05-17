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

      <div className="mb-4 grid grid-cols-2 gap-3">
        <ForecastKpi
          label="예상 공기"
          value={Math.abs(delayDays)}
          unit="일"
          caption={delayDays > 0 ? "지연 예상" : delayDays < 0 ? "단축 예상" : "계획 동일"}
          prefix={delayDays > 0 ? "D+" : delayDays < 0 ? "D−" : ""}
          tone={delayDays > 0 ? "rose" : delayDays < 0 ? "mint" : "ink"}
        />
        <ForecastKpi
          label="최적화 공기"
          value={recoveryDays}
          unit="일"
          caption={recoveryDays > 0 ? "추가 단축 가능" : "추가 단축 불가"}
          prefix={recoveryDays > 0 ? "-" : ""}
          tone="mint"
        />
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

      <div className="mt-4 space-y-1 rounded-md bg-surface-soft/50 px-3 py-2.5 text-sm leading-relaxed text-ink-mid">
        <p>
          <span className="font-semibold text-ink">실적</span>(검정 실선)이{" "}
          <span className="font-semibold text-ink">계획</span>(회색 실선) 대비 어떻게 진행되었는지 보여주며,{" "}
          파란 점선은 현 추세 유지 시 예측, 녹색 점선은 AI 권고 적용 시 만회 시나리오입니다.
        </p>
        <p>📊 {baseNarrative(diagnosis)}</p>
        {recoveryActive && <p>⚡ {recoveryNarrative(diagnosis)}</p>}
      </div>
    </div>
  );
}

function baseNarrative(d: ProductivityDiagnosis): string {
  const sign = d.z_score >= 0 ? "+" : "−";
  const absZ = Math.abs(d.z_score).toFixed(1);
  const within = Math.abs(d.z_score) < 1.5;
  const range = within ? "정상 변동 범위 안" : "정상 변동 범위 밖";
  const eta = d.scenarios.base.eta_days;
  const etaText = Number.isFinite(eta) ? `자연 회귀 시 ${eta}일 회복` : "자연 회귀 불가";
  return `이력 평균 ${sign}${absZ}σ — ${range}, ${etaText}.`;
}

function recoveryNarrative(d: ProductivityDiagnosis): string {
  const opt = d.scenarios.optimistic;
  const baseEta = d.scenarios.base.eta_days;
  if (!Number.isFinite(opt.eta_days)) {
    return `AI 권고 적용 시에도 회복 불가.`;
  }
  if (!Number.isFinite(baseEta)) {
    return `AI 권고 적용 시 ${opt.eta_days}일에 회복 가능.`;
  }
  const cut = baseEta - opt.eta_days;
  return `AI 권고 적용 시 ${cut}일 단축 (${opt.eta_days}일에 회복).`;
}

interface ForecastKpiProps {
  label: string;
  value: number;
  unit: string;
  caption: string;
  prefix?: string;
  tone: "rose" | "mint" | "ink";
}

function ForecastKpi({ label, value, unit, caption, prefix = "", tone }: ForecastKpiProps) {
  const valueTone = {
    rose: "text-rose-text",
    mint: "text-mint-text",
    ink:  "text-ink",
  }[tone];
  return (
    <div className="rounded-card border border-border-soft bg-surface-soft/40 px-4 py-3">
      <div className="text-sm text-ink-mid">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={cn("font-display text-h3 font-semibold tracking-[-0.015em]", valueTone)}>
          {prefix}{value}
        </span>
        <span className="text-base text-ink-light">{unit}</span>
        <span className="ml-1 text-sm text-ink-mid">{caption}</span>
      </div>
    </div>
  );
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
