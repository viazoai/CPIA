import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { HierBox } from "@/app/components/review/board/HierBox";
import { QtyCard } from "@/app/components/review/board/QtyCard";
import type { ReviewItem } from "@/lib/types";

describe("HierBox", () => {
  it("라벨·미확정 배지 표시, 자식 있으면 캐럿(▾/▸)", () => {
    render(<HierBox label="골조" reviewCount={2} hasChildren collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText("골조")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("▾")).toBeTruthy();
  });
  it("collapsed 면 ▸, 클릭 시 onToggle", () => {
    const onToggle = vi.fn();
    render(<HierBox label="골조" reviewCount={0} hasChildren collapsed onToggle={onToggle} />);
    expect(screen.getByText("▸")).toBeTruthy();
    fireEvent.click(screen.getByText("골조"));
    expect(onToggle).toHaveBeenCalled();
  });
  it("자식 없으면 캐럿 없음", () => {
    render(<HierBox label="WP" reviewCount={0} hasChildren={false} collapsed={false} onToggle={() => {}} />);
    expect(screen.queryByText("▾")).toBeNull();
    expect(screen.queryByText("▸")).toBeNull();
  });
});

const item: ReviewItem = {
  id: "c1", idx: 0, bp_name: "대성철근", work_content: "기둥 주근 D25", quantity: 12, unit: "ton",
  ai_mapped_wp_id: "fab-기둥", ai_mapped_path: "p", wa: "FAB", l6_main: "기둥", confidence: 0.62, status: "unconfirmed",
};

describe("QtyCard", () => {
  it("검토(미확정) 카드는 강조(data-review) + 확정 버튼, 클릭 시 onConfirm", () => {
    const onConfirm = vi.fn();
    const { container } = render(<QtyCard item={item} onConfirm={onConfirm} />);
    expect(screen.getByText("대성철근")).toBeTruthy();
    expect(container.querySelector("[data-review='true']")).toBeTruthy();
    fireEvent.click(screen.getByText("확정"));
    expect(onConfirm).toHaveBeenCalledWith("c1");
  });
  it("확정 카드는 강조·확정버튼 없음", () => {
    render(<QtyCard item={{ ...item, status: "confirmed" }} onConfirm={() => {}} />);
    expect(screen.queryByText("확정")).toBeNull();
  });
});
