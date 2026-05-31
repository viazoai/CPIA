"use client";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ReferenceArea } from "recharts";
import type { QuadrantPoint } from "@/lib/types";

// 2026-05-29 (2차): 점·배경 색 = 4사분면 위치 (위험/주의/관찰/정상). status(목록칩) 는 3-tier 별도.
const QUADRANT_COLOR: Record<string, string> = { risk: "#ef4444", caution: "#d97706", watch: "#7a8494", safe: "#0ea76a" };

interface Props {
  points: QuadrantPoint[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
  filter?: "all" | "risk" | "caution" | "safe";
}

// 칩 filter "safe" = 정상 = status "normal".
function statusOf(p: QuadrantPoint): "risk" | "caution" | "normal" {
  return p.status ?? "normal";
}

export function QuadrantScatter({ points, selectedWpId, onSelect, filter = "all" }: Props) {
  const wanted = filter === "safe" ? "normal" : filter; // all|risk|caution|normal
  const visible = filter === "all" ? points : points.filter((p) => statusOf(p) === wanted);

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 20, bottom: 40, left: 50 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
          {/* 2026-05-29 (2차): 배경 4구역 = 점 색과 1:1. 임계 생산성70 / 임팩트50 (_quadrant_of 와 동일).
              위험(저생산·고임팩 빨강) / 주의(저생산 주황) / 관찰(고임팩 회색) / 정상(고생산·저임팩 초록). */}
          <ReferenceArea x1={0}  x2={70}  y1={50} y2={100} fill="#ef4444" fillOpacity={0.06} />
          <ReferenceArea x1={0}  x2={70}  y1={0}  y2={50}  fill="#d97706" fillOpacity={0.06} />
          <ReferenceArea x1={70} x2={100} y1={50} y2={100} fill="#7a8494" fillOpacity={0.05} />
          <ReferenceArea x1={70} x2={100} y1={0}  y2={50}  fill="#0ea76a" fillOpacity={0.06} />
          <ReferenceLine x={70} stroke="#cbd5e1" strokeDasharray="4 4" />
          <ReferenceLine y={50} stroke="#cbd5e1" strokeDasharray="4 4" />
          <XAxis type="number" dataKey="productivity" domain={[0, 100]} name="Productivity" reversed
            label={{ value: "← Productivity (저하 →)", position: "bottom", offset: 0, style: { fontSize: 11, fill: "#7a8494" } }}
            tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
          <YAxis type="number" dataKey="impact" domain={[0, 100]} name="Impact"
            label={{ value: "Impact ↑", angle: -90, position: "left", offset: 0, style: { fontSize: 11, fill: "#7a8494" } }}
            tick={{ fontSize: 10, fill: "#7a8494" }} tickFormatter={(v) => `${v}%`} />
          <ZAxis type="number" dataKey="size" range={[60, 300]} />
          <Tooltip
            contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid #e2e6ed" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as QuadrantPoint;
              return (
                <div className="rounded-md border border-border bg-white px-3 py-2 shadow-md text-[11px]">
                  <div className="font-bold text-ink">{p.wp_name}</div>
                  <div className="text-ink-light">{p.trade}</div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3">
                    <span>Productivity:</span><b>{`${p.productivity.toFixed(1)}%`}</b>
                    <span>Impact:</span><b>{p.impact}%</b>
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={visible} onClick={(e) => onSelect((e as unknown as QuadrantPoint).wp_id)}>
            {visible.map((p, i) => (
              // 2026-05-29 (2차): 점 색 = 4값 quadrant (위치) — 위험/주의/관찰/정상 4색.
              <Cell key={i} fill={QUADRANT_COLOR[p.quadrant] ?? "#7a8494"}
                stroke={p.wp_id === selectedWpId ? "#0d1117" : "transparent"}
                strokeWidth={p.wp_id === selectedWpId ? 2.5 : 0} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
