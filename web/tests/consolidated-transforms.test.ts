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

  it("outputFromBpSummaries: BP사=업체명, zone=companyWa, 금일=work_text_today, 전일/명일=크로스데이트 맵", () => {
    const rows = outputFromBpSummaries(
      [{ company: "광건", bp_code: "PH_X-070", work_text_today: "오늘", today_incr_total: 796 }],
      { 광건: "FAB" },
      { 광건: "어제" },
      { 광건: "내일" },
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].bp_code).toBe("광건");
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].today_work).toBe("오늘");
    expect(rows[0].prev_work).toBe("어제");
    expect(rows[0].next_work).toBe("내일");
  });

  it("outputFromBpSummaries: 크로스데이트 맵에 회사 없으면 전일/명일 빈값", () => {
    const rows = outputFromBpSummaries(
      [{ company: "광건", work_text_today: "오늘", today_incr_total: 1 }],
      {},
      {},
      {},
    );
    expect(rows[0].today_work).toBe("오늘");
    expect(rows[0].prev_work).toBe("");
    expect(rows[0].next_work).toBe("");
  });

  it("reconstructOutputFromMapper: per-company, BP사=업체명, 금일=work_today, 전일/명일=크로스데이트, day=반올림", () => {
    const agg: MapperOutputAgg[] = [
      { company: "OTIS", trade: "건축", workers_total: 27.3, work_today: "오늘작업" },
    ];
    const rows = reconstructOutputFromMapper(agg, { OTIS: "FAB" }, { OTIS: "어제작업" }, {});
    expect(rows[0].bp_code).toBe("OTIS");
    expect(rows[0].zone).toBe("FAB");
    expect(rows[0].trade).toBe("건축");
    expect(rows[0].today_work).toBe("오늘작업");
    expect(rows[0].main_work).toBe("오늘작업");
    expect(rows[0].prev_work).toBe("어제작업");
    expect(rows[0].next_work).toBe(""); // nextMap 에 OTIS 없음
    expect(rows[0].day).toBe(27);
  });

  it("크로스데이트 맵 생략 시(기본 빈 객체) 전일/명일 빈값", () => {
    const agg: MapperOutputAgg[] = [{ company: "A", trade: "토목", workers_total: 5, work_today: "x" }];
    const rows = reconstructOutputFromMapper(agg, {});
    expect(rows[0].prev_work).toBe("");
    expect(rows[0].next_work).toBe("");
  });

  it("결정성: 동일 입력 2회 동일 출력", () => {
    const agg: MapperOutputAgg[] = [{ company: "A", trade: "토목", workers_total: 5, work_today: "x" }];
    expect(reconstructOutputFromMapper(agg, {}, { A: "p" }, { A: "n" }))
      .toEqual(reconstructOutputFromMapper(agg, {}, { A: "p" }, { A: "n" }));
  });
});
