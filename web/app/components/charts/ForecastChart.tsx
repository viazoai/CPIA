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
}

interface ToggleState {
  optimistic: boolean;
  pessimistic: boolean;
  ewma: boolean;
}

export function ForecastChart({ diagnosis, recoveryActive = false }: Props) {
  const [toggles, setToggles] = useState<ToggleState>({
    optimistic: false,
    pessimistic: false,
    ewma: false,
  });

  const showOptimistic = toggles.optimistic || recoveryActive;

  const data = diagnosis.s_curve.map((p, i) => ({
    date: p.date,
    planned: p.planned,
    actual: p.actual,
    band_low:  diagnosis.band_p25[i],
    band_high: diagnosis.band_p75[i],
    ewma:      diagnosis.ewma_trend[i],
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
        <div>
          <div className="font-display text-h6 text-ink">Forecast</div>
          <div className="text-body-sm text-ink-mid">현 추세 + 신뢰 밴드</div>
        </div>
        <ConfidenceBadge sampleSize={diagnosis.sample_size} />
      </div>

      <div className="mb-3 space-y-1 text-body-sm text-ink-mid">
        <p>📊 {baseNarrative(diagnosis)}</p>
        {recoveryActive && (
          <p>⚡ {recoveryNarrative(diagnosis)}</p>
        )}
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
        <ToggleChip
          label="최근 추세 (EWMA)"
          color="ink"
          active={toggles.ewma}
          onClick={() => setToggles((s) => ({ ...s, ewma: !s.ewma }))}
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

          <Line dataKey="planned" stroke="#7a8494" strokeWidth={1.5} dot={false} isAnimationActive={false} />

          <Line dataKey="base" stroke="#1a56db" strokeWidth={2.5} dot={false} isAnimationActive={false} />

          <Line dataKey="actual" stroke="#0d1117" strokeWidth={2} dot={false} isAnimationActive={false} />

          {showOptimistic && (
            <Line dataKey="optimistic" stroke="#0ea76a" strokeWidth={2.5} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          )}

          {toggles.pessimistic && (
            <Line dataKey="pessimistic" stroke="#ef4444" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          )}

          {toggles.ewma && (
            <Line dataKey="ewma" stroke="#444e5e" strokeWidth={1.5} strokeDasharray="2 2" dot={false} isAnimationActive={false} />
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
