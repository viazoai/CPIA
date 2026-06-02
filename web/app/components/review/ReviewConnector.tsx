"use client";
import { useEffect, useState } from "react";

interface Props {
  containerRef: React.RefObject<HTMLElement>;
  selectedCardId: string | null;
  targetNodeId: string | null;        // = 선택 카드의 ai_mapped_wp_id
  tone: "mint" | "sun";
  /** 외부에서 강제 재드로잉 (펼침·모드 전환 등). */
  redrawKey: number;
}

export function ReviewConnector({ containerRef, selectedCardId, targetNodeId, tone, redrawKey }: Props) {
  const [path, setPath] = useState<string | null>(null);

  useEffect(() => {
    const compute = () => {
      const container = containerRef.current;
      if (!container || !selectedCardId || !targetNodeId) {
        setPath(null);
        return;
      }
      const cardEl = container.querySelector(`[data-card-anchor="${CSS.escape(selectedCardId)}"]`);
      const nodeEl = container.querySelector(`[data-wbs-node-id="${CSS.escape(targetNodeId)}"]`);
      if (!cardEl || !nodeEl) {
        setPath(null);
        return;
      }
      const c = container.getBoundingClientRect();
      const cr = cardEl.getBoundingClientRect();
      const nr = nodeEl.getBoundingClientRect();
      const x1 = cr.left - c.left;                 // 카드 왼쪽 가장자리
      const y1 = cr.top - c.top + cr.height / 2;   // 카드 세로 중앙
      const x2 = nr.right - c.left;                // 노드 오른쪽 가장자리
      const y2 = nr.top - c.top + nr.height / 2;   // 노드 세로 중앙
      const dx = Math.max(40, (x1 - x2) * 0.5);
      setPath(`M ${x1} ${y1} C ${x1 - dx} ${y1}, ${x2 + dx} ${y2}, ${x2} ${y2}`);
    };

    compute();

    let raf = 0;
    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(compute);
    };
    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true); // capture: 내부 스크롤 컨테이너 포함
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(schedule) : null;
    if (ro && containerRef.current) ro.observe(containerRef.current);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      ro?.disconnect();
    };
  }, [containerRef, selectedCardId, targetNodeId, redrawKey]);

  if (!path) return null;
  const stroke = tone === "sun" ? "var(--sun, #d8a93a)" : "var(--mint, #16a34a)";

  return (
    <svg
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ overflow: "visible", zIndex: 5 }}
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={2} strokeLinecap="round" />
      <circle cx={path.split(" ")[1]} cy={path.split(" ")[2]} r={3} fill={stroke} />
    </svg>
  );
}
