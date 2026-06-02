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

  it("지연 0일(일정 충족)이면 진단 괄호 미노출 — recovery 0 도 미노출", () => {
    const { queryByText, getByText } = render(
      <OptimizerResult output={out} delayDays={0} recoveryDays={0} />
    );
    // 진단/만회방안 괄호 미노출 (라벨은 순수 텍스트). out.diagnosis="진단" 본문과 겹쳐
    // getByText("진단") 은 ambiguous → 괄호 부재로 검증.
    expect(queryByText(/\(지연/)).toBeNull();
    expect(queryByText(/AI 단축/)).toBeNull();
    expect(getByText("만회방안")).toBeTruthy(); // 괄호 없는 순수 "만회방안"
  });
});
