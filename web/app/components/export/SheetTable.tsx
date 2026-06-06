"use client";
import { cn } from "@/lib/utils";
import type {
  OutputManpowerRow,
  OccupationManpowerRow,
  EquipmentRow,
  QuantityRow,
} from "@/lib/types";

export interface SheetColumn<T> {
  key: keyof T;
  label: string;
  align?: "left" | "right" | "center";
  width?: string;          // ex. "w-24"
  /** 셀 값 커스텀 렌더 (예: 숫자 toLocaleString, 줄바꿈 보존) */
  format?: (v: T[keyof T], row: T) => React.ReactNode;
  /** 셀 추가 className */
  cellClass?: string;
}

interface Props<T extends object> {
  cols: readonly SheetColumn<T>[];
  rows: readonly T[];
}

export function SheetTable<T extends object>({ cols, rows }: Props<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="sticky top-0 bg-surface-soft/95 backdrop-blur-sm">
          <tr>
            {cols.map((c) => (
              <th
                key={String(c.key)}
                className={cn(
                  "border-b border-border px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-ink-light",
                  c.align === "right"  && "text-right",
                  c.align === "center" && "text-center",
                  !c.align && "text-left",
                  c.width
                )}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border-soft hover:bg-surface-soft/50">
              {cols.map((c) => {
                const raw = r[c.key];
                const content = c.format ? c.format(raw, r) : String(raw ?? "");
                return (
                  <td
                    key={String(c.key)}
                    className={cn(
                      "px-3 py-1.5 align-top text-ink-mid",
                      c.align === "right"  && "text-right tabular-nums",
                      c.align === "center" && "text-center"
                    )}
                  >
                    {/* cellClass 는 내부 div 에. line-clamp(display:-webkit-box)를 td 에 직접 걸면
                        display:table-cell 이 깨져 컬럼 정렬이 무너지므로 래퍼로 격리한다. */}
                    {c.cellClass ? <div className={cn(c.cellClass)}>{content}</div> : content}
                  </td>
                );
              })}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={cols.length} className="px-3 py-12 text-center text-ink-light">
                해당 시트에 데이터가 없습니다.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ────── 4 시트별 컬럼 정의 ──────
const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString() : String(v ?? ""));

export const OUTPUT_MANPOWER_COLS: readonly SheetColumn<OutputManpowerRow>[] = [
  { key: "pjt",        label: "PJT" },
  { key: "zone",       label: "Zone" },
  { key: "trade",      label: "공종" },
  { key: "bp_code",    label: "BP사", cellClass: "font-mono text-[11px]" },
  { key: "scope",      label: "Scope" },
  { key: "prev_work",  label: "전일 작업사항", cellClass: "max-w-[160px] whitespace-pre-line line-clamp-3" },
  { key: "today_work", label: "금일 작업사항", cellClass: "max-w-[200px] whitespace-pre-line line-clamp-3 text-ink" },
  { key: "next_work",  label: "명일 작업사항", cellClass: "max-w-[160px] whitespace-pre-line line-clamp-3" },
] as const;

export const OCCUPATION_COLS: readonly SheetColumn<OccupationManpowerRow>[] = [
  { key: "trade",        label: "공종" },
  { key: "bp_code",      label: "BP사", cellClass: "font-mono text-[11px]" },
  { key: "manager_code", label: "관리자", cellClass: "font-mono text-[11px]" },
  { key: "skilled_code", label: "기능공", cellClass: "font-mono text-[11px]" },
  { key: "occupation",   label: "직종" },
  { key: "prev_cum",     label: "전일누계", align: "right", format: num },
  { key: "early",        label: "조출",    align: "right", format: num },
  { key: "day",          label: "주간",    align: "right", format: num },
  { key: "overtime",     label: "연장",    align: "right", format: num },
  { key: "night",        label: "야간",    align: "right", format: num },
  { key: "allnight",     label: "철야",    align: "right", format: num },
  { key: "cum_t",        label: "Cum. T",  align: "right", format: num, cellClass: "font-semibold text-ink" },
] as const;

export const EQUIPMENT_COLS: readonly SheetColumn<EquipmentRow>[] = [
  { key: "trade",     label: "공종" },
  { key: "bp_code",   label: "BP사", cellClass: "font-mono text-[11px]" },
  { key: "eq_major",  label: "대분류" },
  { key: "eq_mid",    label: "중분류" },
  { key: "eq_spec",   label: "규격" },
  { key: "prev_cum",  label: "전일누계", align: "right", format: num },
  { key: "early",     label: "조출",    align: "right", format: num },
  { key: "day",       label: "주간",    align: "right", format: num },
  { key: "overtime",  label: "연장",    align: "right", format: num },
  { key: "night",     label: "야간",    align: "right", format: num },
  { key: "allnight",  label: "철야",    align: "right", format: num },
  { key: "cum_t",     label: "Cum. T",  align: "right", format: num, cellClass: "font-semibold text-ink" },
] as const;

export const QUANTITY_COLS: readonly SheetColumn<QuantityRow>[] = [
  { key: "zone",       label: "Zone" },
  { key: "trade",      label: "공종" },
  { key: "bp_code",    label: "BP 코드", cellClass: "font-mono text-[11px]" },
  { key: "bp_name",    label: "BP사" },
  { key: "scope",      label: "Scope" },
  { key: "rep_work",   label: "대표 작업내용", cellClass: "max-w-[220px] whitespace-normal text-ink" },
  { key: "unit",       label: "단위", align: "center" },
  { key: "total_a",    label: "총물량 [A]",   align: "right", format: num },
  { key: "prev_cum_b", label: "전일누적 [B]", align: "right", format: num },
  { key: "today_c",    label: "금일실적 [C]", align: "right", format: num, cellClass: "font-semibold text-ink" },
] as const;
