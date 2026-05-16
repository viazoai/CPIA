"use client";
import { useState, useMemo } from "react";
import { Search, Download } from "lucide-react";
import type { RawDataRow } from "@/lib/types";

const COLUMNS: { key: keyof RawDataRow; label: string }[] = [
  { key: "building",     label: "건물" },
  { key: "trade",        label: "공종" },
  { key: "wp",           label: "WP" },
  { key: "bp_name",      label: "BP사" },
  { key: "work_content", label: "작업내용" },
  { key: "quantity",     label: "물량" },
  { key: "unit",         label: "단위" },
  { key: "workers",      label: "인원" },
  { key: "equipment",    label: "장비" },
];

export function RawDataTab({ rows }: { rows: RawDataRow[] }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const needle = q.toLowerCase();
    return rows.filter((r) =>
      Object.values(r).some((v) => String(v).toLowerCase().includes(needle))
    );
  }, [rows, q]);

  const exportCsv = () => {
    const header = COLUMNS.map((c) => c.label).join(",");
    const body = filtered.map((r) => COLUMNS.map((c) => JSON.stringify(r[c.key] ?? "")).join(",")).join("\n");
    const csv = `${header}\n${body}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "raw_data.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="rounded-card border border-border-soft bg-card shadow-xs overflow-hidden">
      <div className="flex items-center justify-between p-3 border-b border-border-soft">
        <div className="font-mono text-xs uppercase tracking-wider text-ink-light">
          작업일보 매핑 결과 · {rows.length} rows
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-light" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="검색..."
              className="rounded-md border border-border bg-white pl-7 pr-2 py-1 text-xs text-ink placeholder:text-ink-light focus:border-lavender focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={exportCsv}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-white px-2.5 py-1 text-xs font-semibold text-ink-mid hover:bg-surface-soft"
          >
            <Download className="h-3 w-3" />
            CSV
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead className="bg-surface-soft">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className="px-2 py-2 text-left font-mono uppercase tracking-wider text-ink-light text-xs">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i} className="border-t border-border-soft hover:bg-surface-soft/50">
                {COLUMNS.map((c) => (
                  <td key={c.key} className="px-2 py-1.5 text-ink-mid">
                    {String(r[c.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="px-2 py-8 text-center text-ink-light">검색 결과 없음</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
