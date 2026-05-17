"use client";
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ReferenceArea } from "recharts";
import type { QuadrantPoint } from "@/lib/types";

const QUADRANT_COLOR = { risk: "#ef4444", caution: "#d97706", watch: "#7a8494", safe: "#0ea76a" };

interface Props {
  points: QuadrantPoint[];
  selectedWpId: string | null;
  onSelect: (wpId: string) => void;
  filter?: "all" | "risk" | "caution" | "safe";
}

export function QuadrantScatter({ points, selectedWpId, onSelect, filter = "all" }: Props) {
  const visible = filter === "all" ? points : points.filter((p) => p.quadrant === filter);

  return (
    <div className="w-full h-72">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 20, bottom: 40, left: 50 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" />
          <ReferenceArea x1={0}  x2={70} y1={70} y2={100} fill="#ef4444" fillOpacity={0.05} />
          <ReferenceArea x1={70} x2={100} y1={70} y2={100} fill="#d97706" fillOpacity={0.05} />
          <ReferenceArea x1={0}  x2={70} y1={0}  y2={70}  fill="#7a8494" fillOpacity={0.03} />
          <ReferenceArea x1={70} x2={100} y1={0}  y2={70}  fill="#0ea76a" fillOpacity={0.05} />
          <ReferenceLine x={70} stroke="#cbd5e1" strokeDasharray="4 4" />
          <ReferenceLine y={70} stroke="#cbd5e1" strokeDasharray="4 4" />
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
                    <span>Productivity:</span><b>{p.productivity}%</b>
                    <span>Impact:</span><b>{p.impact}%</b>
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={visible} onClick={(e) => onSelect((e as unknown as QuadrantPoint).wp_id)}>
            {visible.map((p, i) => (
              <Cell key={i} fill={QUADRANT_COLOR[p.quadrant]}
                stroke={p.wp_id === selectedWpId ? "#0d1117" : "transparent"}
                strokeWidth={p.wp_id === selectedWpId ? 2.5 : 0} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
