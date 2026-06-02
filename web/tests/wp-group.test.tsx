import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WpGroup } from "@/app/components/review/WpGroup";
import { groupCardsByWp } from "@/lib/review-group";
import type { ReviewItem, WBSNode } from "@/lib/types";

const wbs: WBSNode = { id: "s", type: "building", name: "s", parent_id: null, review_count: 0, total_count: 0, status: "normal", children: [] };
const mk = (over: Partial<ReviewItem>): ReviewItem => ({
  id: "x", idx: 0, bp_name: "BP", work_content: "작업내용", quantity: 1, unit: "EA",
  ai_mapped_wp_id: "wp1", ai_mapped_path: "M15X > FAB > 기둥배근",
  wa: "FAB", l6_main: "기둥배근", confidence: 0.6, status: "unconfirmed", ...over,
});
const noop = () => {};

describe("WpGroup (HIL)", () => {
  it("헤더에 확정·미확정 집계 표기, 미확정 카드 풀 노출", () => {
    const [g] = groupCardsByWp([
      mk({ id: "u1", status: "unconfirmed", confidence: 0.6 }),
      mk({ id: "c1", status: "confirmed", confidence: 0.95 }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} />);
    expect(screen.getByText(/미확정/)).toBeTruthy();
    expect(screen.getByText("기둥배근")).toBeTruthy();
    expect(screen.getByText(/확정 1건/)).toBeTruthy();
  });

  it("확정 접힘 토글 클릭 시 확정 카드 노출", () => {
    const [g] = groupCardsByWp([
      mk({ id: "u1", status: "unconfirmed" }),
      mk({ id: "c1", status: "confirmed", bp_name: "확정BP" }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} />);
    expect(screen.queryByText("확정BP")).toBeNull();
    fireEvent.click(screen.getByText(/확정 1건/));
    expect(screen.getByText("확정BP")).toBeTruthy();
  });
});

describe("WpGroup (등록/readOnly)", () => {
  it("readOnly 면 헤더 '등록 N건', 전 항목 노출(접힘 없음)", () => {
    const [g] = groupCardsByWp([
      mk({ id: "r1", status: "confirmed", bp_name: "등록BP1" }),
      mk({ id: "r2", status: "confirmed", bp_name: "등록BP2" }),
    ]);
    render(<WpGroup group={g} selectedCardId={null} wbsRoot={wbs} onConfirm={noop} onRemap={noop} onSelectCard={noop} readOnly />);
    expect(screen.getByText(/등록 2건/)).toBeTruthy();
    expect(screen.getByText("등록BP1")).toBeTruthy();
    expect(screen.getByText("등록BP2")).toBeTruthy();
  });
});
