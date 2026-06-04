import { describe, it, expect } from "vitest";
import {
  bpLabel,
  outputFromBpSummaries,
  reconstructOutputFromMapper,
  type MapperOutputAgg,
} from "@/lib/consolidated-transforms";

describe("consolidated-transforms", () => {
  it("bpLabel: 업체명 우선, 코드 폴백, 둘 다 없으면 빈문자", () => {
    expect(bpLabel("광건", "PH_X-070")).toBe("광건");
    expect(bpLabel(null, "PH_X-070")).toBe("PH_X-070");
    expect(bpLabel("", "PH_X-070")).toBe("PH_X-070");
    expect(bpLabel(undefined, undefined)).toBe("");
  });

  it("outputFromBpSummaries: 9/25 — BP사=업체명(코드 아님), per-company 유지, zone=companyWa", () => {
    const rows = outputFromBpSummaries(
      [{ company: "광건", bp_code: "PH_X-070", work_text_today: "A\nB", today_incr_total: 796 }],
      { 광건: "FAB" },
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].bp_code).toBe("광건"); // 코드 PH_X-070 아님
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].today_work).toBe("A\nB");
    expect(rows[0].prev_work).toBe(""); // work_text_yesterday 없으면 빈값
  });

  it("reconstructOutputFromMapper: 시드 — per-company, BP사=업체명, 전일/명일 빈값, day=반올림 인원", () => {
    const agg: MapperOutputAgg[] = [
      { company: "OTIS", trade: "건축", workers_total: 27.3, work_today: "승강로 작업" },
    ];
    const rows = reconstructOutputFromMapper(agg, { OTIS: "FAB" });
    expect(rows[0].bp_code).toBe("OTIS"); // 업체명
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].trade).toBe("건축");
    expect(rows[0].today_work).toBe("승강로 작업");
    expect(rows[0].main_work).toBe("승강로 작업");
    expect(rows[0].prev_work).toBe("");
    expect(rows[0].next_work).toBe("");
    expect(rows[0].day).toBe(27);
  });

  it("결정성: 동일 입력 2회 동일 출력", () => {
    const agg: MapperOutputAgg[] = [{ company: "A", trade: "토목", workers_total: 5, work_today: "x" }];
    expect(reconstructOutputFromMapper(agg, {})).toEqual(reconstructOutputFromMapper(agg, {}));
  });
});
