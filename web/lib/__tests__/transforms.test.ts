import { describe, it, expect, beforeEach, vi } from "vitest";
import sql from "@/lib/pg";
import {
  deriveProgressPercent,
  deriveYearlySaving,
  deriveItemStatus,
  deriveWpIdAndPath,
  deriveImpact,
  deriveStageProgress,
  wbsTreeBuild,
  deriveChatSequence,
} from "../transforms";

describe("G12 deriveProgressPercent", () => {
  it.each([
    [{ status: "completed", current_node: null }, 100],
    [{ status: "running", current_node: "optimizer" }, 90],
    [{ status: "running", current_node: "forecaster" }, 80],
    [{ status: "running", current_node: "exporter" }, 70],
    [{ status: "running", current_node: "atomizer" }, 60],
    [{ status: "waiting_hil_1", current_node: "mapper" }, 50],
    [{ status: "running", current_node: "mapper" }, 30],
    [{ status: "running", current_node: "parser" }, 20],
    [{ status: "running", current_node: null }, 0],
  ])("%o → %d", (input, expected) => {
    expect(deriveProgressPercent(input.status, input.current_node)).toBe(expected);
  });
});

describe("G1 deriveYearlySaving", () => {
  it("산식: fte*1.5 + hours*rate/1e8 → 단위 억", () => {
    // 15.4 * 1.5 + 2155 * 50000 / 1e8 = 23.1 + 1.0775 = 24.1775
    expect(deriveYearlySaving(15.4, 2155)).toBeCloseTo(24.18, 1);
  });
  it("custom hourlyRate", () => {
    expect(deriveYearlySaving(10, 1000, 60000)).toBeCloseTo(
      10 * 1.5 + (1000 * 60000) / 1e8,
      3,
    );
  });
});

describe("G11 deriveItemStatus", () => {
  it("Mapper requires_review true → hil_pending", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: true, mapping_conf: 0.4 }),
    ).toBe("hil_pending");
  });
  it("Mapper mapping_conf >= 0.7 → done", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.85 }),
    ).toBe("done");
  });
  it("Mapper 0.4 <= mapping_conf < 0.7 → processing", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.5 }),
    ).toBe("processing");
  });
  it("Mapper mapping_conf < 0.4 → received", () => {
    expect(
      deriveItemStatus("Mapper", { requires_review: false, mapping_conf: 0.2 }),
    ).toBe("received");
  });
  it("HIL Review has_correction → done", () => {
    expect(deriveItemStatus("HIL Review", { has_correction: true })).toBe("done");
  });
  it("HIL Review no correction → hil_pending", () => {
    expect(deriveItemStatus("HIL Review", { has_correction: false })).toBe(
      "hil_pending",
    );
  });
  it("risk_level=='이상' → blocked (모든 stage)", () => {
    expect(
      deriveItemStatus("Mapper", { risk_level: "이상", mapping_conf: 0.9 }),
    ).toBe("blocked");
  });
});

describe("G17 deriveWpIdAndPath", () => {
  it("wa+l6_main 조합", () => {
    expect(deriveWpIdAndPath("FAB", "철근콘크리트공사", "M15X Ph-3 IBL")).toEqual({
      wp_id: "fab-철근콘크리트공사",
      wp_name: "FAB 철근콘크리트공사",
      path: "M15X Ph-3 IBL > FAB > 철근콘크리트공사",
    });
  });
  it("null 입력 시 unknown", () => {
    expect(deriveWpIdAndPath(null, null, "site")).toEqual({
      wp_id: "unknown-unknown",
      wp_name: "",
      path: "site",
    });
  });
});

describe("G18 deriveImpact", () => {
  it("normalize to 0~100", () => {
    expect(deriveImpact(1e4, 1e3)).toBe(10); // 1e7 / 1e8 * 100 = 10
  });
  it("over normMax clamp 100", () => {
    expect(deriveImpact(1e6, 1e3)).toBe(100);
  });
  it("null 입력 → 0", () => {
    expect(deriveImpact(null, 100)).toBe(0);
    expect(deriveImpact(100, null)).toBe(0);
  });
});


describe("G10 deriveStageProgress", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("8 단계 배열 + Mapper percent 계산", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        parser_reports: 1,
        parser_acts: 100,
        mapper_acts: 80,
        hil_received: 10,
        hil_done: 4,
        atomized: 70,
        exporter: 1,
        forecasts_done: 60,
        opt_received: 5,
        opt_done: 3,
      },
    ]);
    const r = await deriveStageProgress("2026-05-15");
    expect(r).toHaveLength(8);
    expect(r[0].agent).toBe("Collector");
    expect(r[2].agent).toBe("Mapper");
    // mapper 80/100 = 80%
    expect(r[2].percent).toBe(80);
    // HIL 4/10 = 40%, waiting true
    expect(r[3].agent).toBe("HIL Review");
    expect(r[3].percent).toBe(40);
    expect(r[3].waiting_hil).toBe(true);
    expect(r[3].is_hil).toBe(true);
  });
});


describe("G22 wbsTreeBuild", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("빈 결과 → root only", async () => {
    (sql as any).mockResolvedValueOnce([]);
    const r = await wbsTreeBuild("m15x");
    expect(r.id).toBe("m15x");
    expect(r.children).toEqual([]);
    expect(r.review_count).toBe(0);
  });
  it("4 레벨 트리 (site → wa → l5 → l6) + review_count rollup", async () => {
    (sql as any).mockResolvedValueOnce([
      { wa: "FAB", l5_disc: "골조", l6_main: "거푸집", review_count: 2, worst_risk: 2 },
      { wa: "FAB", l5_disc: "골조", l6_main: "철근", review_count: 1, worst_risk: 3 },
      { wa: "FAB", l5_disc: "마감", l6_main: "도장", review_count: 0, worst_risk: 1 },
    ]);
    const r = await wbsTreeBuild("m15x");
    expect(r.review_count).toBe(3);
    expect(r.children).toHaveLength(1); // FAB
    const fab = r.children![0];
    expect(fab.name).toBe("FAB");
    expect(fab.review_count).toBe(3);
    expect(fab.children).toHaveLength(2); // 골조 + 마감
    const goljo = fab.children!.find((c) => c.name === "골조")!;
    expect(goljo.review_count).toBe(3);
    expect(goljo.children).toHaveLength(2); // 거푸집 + 철근
    const magam = fab.children!.find((c) => c.name === "마감")!;
    expect(magam.children![0].status).toBe("risk"); // worst_risk=1 → 이상 → risk
  });
});

describe("G4 deriveChatSequence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  it("run 없음 → []", async () => {
    (sql as any).mockResolvedValueOnce([]);
    const r = await deriveChatSequence("nope");
    expect(r).toEqual([]);
  });
  it("정상 run → 8 메시지 + HIL 0 → info 타입", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        started_at: new Date("2026-05-15T09:00:00Z"),
        status: "completed",
        parser_count: 100,
        mapper_count: 100,
        hil_count: 0,
        atomized_count: 100,
        reporter_count: 1,
        forecast_count: 80,
        abnormal_count: 0,
        optimizer_count: 0,
      },
    ]);
    const r = await deriveChatSequence("run-1");
    expect(r).toHaveLength(8);
    expect(r[0].agent).toBe("Collector");
    expect(r[2].agent).toBe("Mapper");
    expect(r[2].type).toBe("info");
    expect(r[3].agent).toBe("HIL Review");
    expect(r[7].agent).toBe("Optimizer");
  });
  it("HIL 발생 + 이상 risk → Mapper type=hil_request, Forecaster type=result", async () => {
    (sql as any).mockResolvedValueOnce([
      {
        started_at: new Date("2026-05-15T09:00:00Z"),
        status: "completed",
        parser_count: 100,
        mapper_count: 100,
        hil_count: 5,
        atomized_count: 95,
        reporter_count: 1,
        forecast_count: 80,
        abnormal_count: 3,
        optimizer_count: 3,
      },
    ]);
    const r = await deriveChatSequence("run-2");
    expect(r[2].type).toBe("hil_request");
    expect(r[6].type).toBe("result");
  });
});

