import { describe, it, expect } from "vitest";
import { statusFromZ } from "@/lib/diagnosis";

describe("statusFromZ", () => {
  it("|Z| < 1 → normal", () => {
    expect(statusFromZ(0)).toBe("normal");
    expect(statusFromZ(0.99)).toBe("normal");
    expect(statusFromZ(-0.99)).toBe("normal");
  });
  it("1 ≤ |Z| < 2 → caution", () => {
    expect(statusFromZ(1)).toBe("caution");
    expect(statusFromZ(-1.5)).toBe("caution");
    expect(statusFromZ(1.99)).toBe("caution");
  });
  it("|Z| ≥ 2 → risk", () => {
    expect(statusFromZ(2)).toBe("risk");
    expect(statusFromZ(-3)).toBe("risk");
  });
});
