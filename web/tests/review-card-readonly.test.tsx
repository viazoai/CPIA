import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReviewCard } from "@/app/components/review/ReviewCard";
import type { ReviewItem, WBSNode } from "@/lib/types";

const wbs: WBSNode = { id: "s", type: "building", name: "s", parent_id: null, review_count: 0, total_count: 0, status: "normal", children: [] };
const item: ReviewItem = {
  id: "r1", idx: 1, bp_name: "A건설", work_content: "작업", quantity: 10, unit: "m3",
  ai_mapped_wp_id: "w", ai_mapped_path: "s > FAB > PC", wa: "FAB", l6_main: "PC공사",
  confidence: 0.9, status: "confirmed",
};

describe("ReviewCard readOnly", () => {
  it("readOnly 면 확정·수정 버튼 없고 배지 '등록'", () => {
    render(<ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} readOnly />);
    expect(screen.queryByText("수정")).toBeNull();
    expect(screen.queryByText("확정")).toBeNull();
    expect(screen.getByText("등록")).toBeTruthy();
  });
  it("readOnly 아니면 수정 버튼 있음", () => {
    render(<ReviewCard item={{ ...item, status: "unconfirmed" }} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} />);
    expect(screen.getByText("수정")).toBeTruthy();
  });
});

describe("ReviewCard 선택/앵커", () => {
  it("data-card-anchor 에 item.id 부여", () => {
    const { container } = render(
      <ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} />
    );
    expect(container.querySelector(`[data-card-anchor="r1"]`)).toBeTruthy();
  });

  it("본문 클릭 시 onSelectCard(item.id) 호출", () => {
    const onSelectCard = vi.fn();
    render(
      <ReviewCard item={item} wbsRoot={wbs} onConfirm={() => {}} onRemap={() => {}} onSelectCard={onSelectCard} />
    );
    fireEvent.click(screen.getByText(/작업/));
    expect(onSelectCard).toHaveBeenCalledWith("r1");
  });

  it("확정 버튼 클릭은 onConfirm 만 (선택 버블링 차단)", () => {
    const onSelectCard = vi.fn();
    const onConfirm = vi.fn();
    render(
      <ReviewCard
        item={{ ...item, status: "unconfirmed" }}
        wbsRoot={wbs}
        onConfirm={onConfirm}
        onRemap={() => {}}
        onSelectCard={onSelectCard}
      />
    );
    fireEvent.click(screen.getByText("확정"));
    expect(onConfirm).toHaveBeenCalledWith("r1");
    expect(onSelectCard).not.toHaveBeenCalled();
  });
});
