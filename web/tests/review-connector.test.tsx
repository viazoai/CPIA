import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { createRef } from "react";
import { ReviewConnector } from "@/app/components/review/ReviewConnector";

function Harness(props: { selectedCardId: string | null; targetNodeId: string | null }) {
  const ref = createRef<HTMLDivElement>();
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div data-card-anchor="c1">card</div>
      <div data-wbs-node-id="n1">node</div>
      <ReviewConnector
        containerRef={ref}
        selectedCardId={props.selectedCardId}
        targetNodeId={props.targetNodeId}
        tone="sun"
        redrawKey={0}
      />
    </div>
  );
}

describe("ReviewConnector", () => {
  it("선택 없으면 path 미렌더", () => {
    const { container } = render(<Harness selectedCardId={null} targetNodeId={null} />);
    expect(container.querySelector("path")).toBeNull();
  });
  it("선택+타깃 있으면 path 1개 렌더", () => {
    const { container } = render(<Harness selectedCardId="c1" targetNodeId="n1" />);
    expect(container.querySelector("path")).toBeTruthy();
  });
});
