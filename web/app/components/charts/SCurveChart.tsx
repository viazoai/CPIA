"use client";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceDot } from "recharts";
import type { SCurvePoint } from "@/lib/types";

interface Props {
  points: SCurvePoint[];
  showRecovery?: boolean;
}

export function SCurveChart({ points, showRecovery = true }: Props) {
  const lastActualIdx = points.reduce((acc, p, i) => p.actual !== undefined ? i : acc, -1);
  const lastActualPoint = lastActualIdx >= 0 ? points[lastActualIdx] : null;

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(d) => d.slice(5)} />
          <YAxis tick={{ fontSize: 10, fill: "#7a8494" }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            formatter={(v, n) => {
              const labels: Record<string, string> = { planned: "계획", actual: "실적", forecast: "예측 (현 추세)", recovery: "만회 (Optimizer)" };
              const key = String(n ?? "");
              return [`${v}%`, labels[key] || key];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            formatter={(v) => {
              const labels: Record<string, string> = { planned: "계획선", actual: "실적선", forecast: "예측선 (현 추세)", recovery: "만회선 (Optimizer 시나리오)" };
              return labels[v] || v;
            }}
          />
          <Line type="monotone" dataKey="planned"  stroke="#7a8494" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="actual"   stroke="#0ea76a" strokeWidth={2.5} dot={{ r: 3 }} connectNulls />
          <Line type="monotone" dataKey="forecast" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls />
          {showRecovery && (
            <Line type="monotone" dataKey="recovery" stroke="#1a56db" strokeWidth={2} strokeDasharray="2 3" dot={false} connectNulls />
          )}
          {lastActualPoint && (
            <ReferenceDot x={lastActualPoint.date} y={lastActualPoint.actual!} r={6} fill="#0ea76a" stroke="#fff" strokeWidth={2} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
