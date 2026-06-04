import { describe, it, expect } from "vitest";
import { OUTPUT_MANPOWER_COLS } from "@/app/components/export/SheetTable";

const cell = (key: string) =>
  OUTPUT_MANPOWER_COLS.find((c) => c.key === key)?.cellClass ?? "";

describe("OUTPUT_MANPOWER_COLS 작업사항 셀 계약", () => {
  it("전일/금일/명일 셋 다 whitespace-pre-line + line-clamp-3, truncate 없음", () => {
    for (const k of ["prev_work", "today_work", "next_work"]) {
      expect(cell(k), `${k} pre-line`).toContain("whitespace-pre-line");
      expect(cell(k), `${k} clamp`).toContain("line-clamp-3");
      expect(cell(k), `${k} no-truncate`).not.toContain("truncate");
    }
  });
  it("BP사 라벨은 그대로(마크업 불변 — 디자인 보존)", () => {
    const bp = OUTPUT_MANPOWER_COLS.find((c) => c.key === "bp_code");
    expect(bp?.label).toBe("BP사");
  });
});
