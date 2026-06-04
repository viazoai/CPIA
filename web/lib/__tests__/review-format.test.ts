import { describe, it, expect } from "vitest";
import { formatReviewQuantity } from "../review-format";

describe("formatReviewQuantity", () => {
  it("1000 이상 — 소수점 절삭 + 천단위 콤마", () => {
    expect(formatReviewQuantity(15743.3)).toBe("15,743");
    expect(formatReviewQuantity(1573.3)).toBe("1,573");
    expect(formatReviewQuantity(101059.2)).toBe("101,059");
  });

  it("1000 이상 정수 — 천단위 콤마", () => {
    expect(formatReviewQuantity(4800)).toBe("4,800");
    expect(formatReviewQuantity(1000)).toBe("1,000"); // 경계값 1000 포함
  });

  it("1000 미만 — 원래 값 그대로(소수점 유지, 콤마 없음)", () => {
    expect(formatReviewQuantity(573.3)).toBe("573.3");
    expect(formatReviewQuantity(138.98)).toBe("138.98");
    expect(formatReviewQuantity(2.7)).toBe("2.7");
    expect(formatReviewQuantity(304)).toBe("304");
    expect(formatReviewQuantity(999.99)).toBe("999.99"); // 경계값 직전
  });
});
