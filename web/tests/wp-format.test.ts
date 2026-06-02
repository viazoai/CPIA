import { describe, it, expect } from "vitest";
import { waCode } from "@/lib/wp-format";

describe("waCode", () => {
  it("wp_name '{trade} · {WA}' 에서 WA 추출", () => {
    expect(waCode({ wp_name: "철근콘크리트공사 · CUB", wp_id: "cub-철근콘크리트공사-남웅건설" })).toBe("CUB");
    expect(waCode({ wp_name: "배수 공사 · FAB", wp_id: "fab-배수-공사-장평건설" })).toBe("FAB");
  });
  it("wp_name 에 ' · ' 없으면 wp_id 첫 세그먼트 대문자 폴백", () => {
    expect(waCode({ wp_name: "이상한이름", wp_id: "fab-x-y" })).toBe("FAB");
  });
});
