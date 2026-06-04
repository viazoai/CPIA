import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { SheetTable, OUTPUT_MANPOWER_COLS } from "@/app/components/export/SheetTable";
import type { OutputManpowerRow } from "@/lib/types";

// 회귀: line-clamp(display:-webkit-box)를 <td> 에 직접 걸면 display:table-cell 이 깨져
// 작업사항 3개 열이 같은 x 로 겹쳐 쌓이고 금일/명일 컬럼이 비어 보였다(라이브 geometry 로 확인).
// fix = cellClass 를 td 가 아닌 내부 래퍼 div 로 격리. 이 테스트가 그 격리를 고정한다.
describe("SheetTable 작업사항 셀 레이아웃 회귀", () => {
  const rows: OutputManpowerRow[] = [
    {
      pjt: "M15X",
      zone: "FAB",
      trade: "건축",
      bp_code: "광건",
      scope: "",
      main_work: "오늘",
      prev_work: "어제",
      today_work: "오늘",
      next_work: "내일",
      early: 0,
      day: 1,
      overtime: 0,
    },
  ];

  it("line-clamp 는 td 가 아닌 내부 래퍼에 — td 의 table-cell 보존(컬럼 정렬 깨짐 방지)", () => {
    const { container } = render(<SheetTable cols={OUTPUT_MANPOWER_COLS} rows={rows} />);
    const tds = Array.from(container.querySelectorAll("tbody td"));
    // td 자체에 line-clamp-3 이 있으면 display:-webkit-box 가 table-cell 을 덮어쓴다.
    const clampOnTd = tds.filter((td) => td.classList.contains("line-clamp-3"));
    expect(clampOnTd.length, "line-clamp-3 이 td 에 직접 걸리면 안 됨").toBe(0);
    // 전일/금일/명일 3개 셀 내부 래퍼에 line-clamp-3 이 있어야 한다.
    const clampInside = container.querySelectorAll("tbody td .line-clamp-3");
    expect(clampInside.length, "작업사항 셀 내부 래퍼에 line-clamp-3 존재해야").toBeGreaterThanOrEqual(3);
  });
});
