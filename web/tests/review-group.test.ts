import { describe, it, expect } from "vitest";
import { groupCardsByWp } from "@/lib/review-group";
import type { ReviewItem } from "@/lib/types";

const mk = (over: Partial<ReviewItem>): ReviewItem => ({
  id: "x", idx: 0, bp_name: "BP", work_content: "w", quantity: 1, unit: "EA",
  ai_mapped_wp_id: "wp1", ai_mapped_path: "M15X > FAB > 기둥배근",
  wa: "FAB", l6_main: "기둥배근", confidence: 0.9, status: "unconfirmed",
  ...over,
});

describe("groupCardsByWp", () => {
  it("같은 wp_id 끼리 한 그룹으로 묶고 wpName/path 를 path 에서 분리", () => {
    const groups = groupCardsByWp([
      mk({ id: "a", ai_mapped_wp_id: "wp1" }),
      mk({ id: "b", ai_mapped_wp_id: "wp1" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].wpId).toBe("wp1");
    expect(groups[0].wpName).toBe("기둥배근");
    expect(groups[0].path).toBe("M15X > FAB");
    expect(groups[0].items).toHaveLength(2);
  });

  it("집계: 확정/미확정 카운트 + 미확정 최저 확신도", () => {
    const [g] = groupCardsByWp([
      mk({ id: "a", status: "unconfirmed", confidence: 0.62 }),
      mk({ id: "b", status: "unconfirmed", confidence: 0.58 }),
      mk({ id: "c", status: "confirmed", confidence: 0.95 }),
    ]);
    expect(g.unconfirmedCount).toBe(2);
    expect(g.confirmedCount).toBe(1);
    expect(g.minUnconfirmedConfidence).toBeCloseTo(0.58);
    expect(g.allConfirmed).toBe(false);
  });

  it("정렬: 미확정 포함 그룹이 위(최저확신도 오름차순), 전부확정 그룹은 아래(이름순)", () => {
    const groups = groupCardsByWp([
      mk({ id: "z", ai_mapped_wp_id: "wpZ", ai_mapped_path: "M15X > Z", status: "confirmed" }),
      mk({ id: "a", ai_mapped_wp_id: "wpA", ai_mapped_path: "M15X > A", status: "unconfirmed", confidence: 0.7 }),
      mk({ id: "b", ai_mapped_wp_id: "wpB", ai_mapped_path: "M15X > B", status: "unconfirmed", confidence: 0.5 }),
    ]);
    expect(groups.map((g) => g.wpId)).toEqual(["wpB", "wpA", "wpZ"]);
  });

  it("그룹 내 항목은 미확정(확신도 오름차순) 먼저, 그다음 확정", () => {
    const [g] = groupCardsByWp([
      mk({ id: "c1", status: "confirmed", confidence: 0.99 }),
      mk({ id: "u1", status: "unconfirmed", confidence: 0.8 }),
      mk({ id: "u2", status: "unconfirmed", confidence: 0.6 }),
    ]);
    expect(g.items.map((i) => i.id)).toEqual(["u2", "u1", "c1"]);
  });

  it("path 에 구분자 없으면 wpName=path, path=''", () => {
    const [g] = groupCardsByWp([mk({ ai_mapped_path: "단일" })]);
    expect(g.wpName).toBe("단일");
    expect(g.path).toBe("");
  });
});
