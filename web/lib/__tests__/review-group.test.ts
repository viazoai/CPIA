import { describe, it, expect } from "vitest";
import { groupCardsByL7 } from "../review-group";
import type { ReviewItem } from "../types";

// 테스트용 ReviewItem 팩토리 — 필수 필드만 채우고 나머지 기본값.
function mk(p: Partial<ReviewItem>): ReviewItem {
  return {
    id: p.id ?? Math.random().toString(36).slice(2),
    idx: -1,
    bp_name: p.bp_name ?? "남웅건설",
    work_content: p.work_content ?? "타설",
    quantity: p.quantity ?? 0,
    unit: p.unit ?? "m3",
    ai_mapped_wp_id: p.ai_mapped_wp_id ?? "fab-철근콘크리트공사",
    ai_mapped_path: p.ai_mapped_path ?? "M15X > FAB > 철근콘크리트공사 > 타설",
    wa: p.wa ?? "FAB",
    l6_main: p.l6_main ?? "철근콘크리트공사",
    confidence: p.confidence ?? 1.0,
    status: p.status ?? "confirmed",
    l7_label: p.l7_label,
    alternative_wps: [],
  };
}

describe("groupCardsByL7", () => {
  it("l7_label 로 묶고 그룹명=l7, 같은 (wa,l6) 내 복수 l7 분리", () => {
    const cards = [
      mk({ l7_label: "거푸집공사", quantity: 100, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > 기초공사 : 거푸집 공사" }),
      mk({ l7_label: "거푸집공사", quantity: 50, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > RC : 거푸집 공사" }),
      mk({ l7_label: "철근공사", quantity: 80, ai_mapped_path: "M15X > FAB > 철근콘크리트공사 > 기초공사 : 철근 조립" }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups.map((g) => g.wpName)).toEqual(["거푸집공사", "철근공사"]); // Σqty: 거푸집150 > 철근80
    expect(groups[0].items).toHaveLength(2);
    expect(groups[0].path).toBe("M15X > FAB > 철근콘크리트공사");
    // wpId 고유 (key 충돌 방지)
    expect(new Set(groups.map((g) => g.wpId)).size).toBe(2);
  });

  it("빈/누락 l7_label → '기타' 그룹", () => {
    const cards = [
      mk({ l7_label: undefined, quantity: 10 }),
      mk({ l7_label: "", quantity: 5 }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups).toHaveLength(1);
    expect(groups[0].wpName).toBe("기타");
  });

  it("같은 l7명이 서로 다른 (wa,l6) → 별도 그룹 (오병합 방지)", () => {
    const cards = [
      mk({ l7_label: "콘크리트공사", ai_mapped_wp_id: "fab-철근콘크리트공사", wa: "FAB", quantity: 100 }),
      mk({ l7_label: "콘크리트공사", ai_mapped_wp_id: "cub-철근콘크리트공사", wa: "CUB", quantity: 30 }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups).toHaveLength(2);
    expect(new Set(groups.map((g) => g.wpId)).size).toBe(2);
  });

  it("그룹 내 카드 quantity DESC 정렬", () => {
    const cards = [
      mk({ l7_label: "콘크리트공사", quantity: 5, work_content: "작음" }),
      mk({ l7_label: "콘크리트공사", quantity: 99, work_content: "큼" }),
    ];
    const groups = groupCardsByL7(cards);
    expect(groups[0].items.map((c) => c.work_content)).toEqual(["큼", "작음"]);
  });
});
