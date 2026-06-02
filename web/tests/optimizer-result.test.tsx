import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { OptimizerResult } from "@/app/components/reports/OptimizerResult";
import type { OptimizerOutput } from "@/lib/types";

const out: OptimizerOutput = {
  wp_id: "x", diagnosis: "진단", similar_cases: [],
  recommendations: [{ rank: 1, keyword: "교대근무", action: "인력 추가 배치", reason: "이유" }],
  details: [],
};

describe("OptimizerResult 권고 마커", () => {
  it("li 의 첫 자식이 블록 div 가 아니라 inline (마커와 본문 동일 라인)", () => {
    const { container } = render(<OptimizerResult output={out} />);
    const li = container.querySelector("li");
    expect(li).toBeTruthy();
    // 첫 element 자식이 SPAN(inline) 이어야 한다 (DIV 면 마커가 줄바꿈됨)
    const firstEl = li!.querySelector(":scope > *");
    expect(firstEl?.tagName).toBe("SPAN");
  });

  it("권고사항 라벨이 '만회방안' + 괄호에 지연/AI단축", () => {
    const { getByText } = render(
      <OptimizerResult output={out} delayDays={31} recoveryDays={2} />
    );
    expect(getByText(/만회방안/)).toBeTruthy();
    expect(getByText(/\(지연 \+31일\)/)).toBeTruthy();
    expect(getByText(/\(AI 단축 -2일\)/)).toBeTruthy();
  });
});
