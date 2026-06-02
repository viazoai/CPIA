"use client";
import { useMemo, useState, useCallback } from "react";
import {
  ReactFlow, ReactFlowProvider, Background, Controls,
  useReactFlow, type Node, type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { CheckCheck } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { buildBoardGraph } from "@/lib/board-graph";
import { layoutBoard } from "@/lib/board-layout";
import { HierNode } from "./board/HierNode";
import { QtyNode } from "./board/QtyNode";
import type { WBSNode, ReviewItem } from "@/lib/types";

interface Props {
  wbs: WBSNode;
  cards: ReviewItem[];
  onConfirm: (id: string) => void;
  onConfirmHighConf: () => void;
  onConfirmAll: () => void;
  onRemap: (id: string, newWpId: string, newPath: string) => void;
}

const nodeTypes = { hier: HierNode, qty: QtyNode } as const;

function BoardInner({ wbs, cards, onConfirm, onConfirmHighConf, onConfirmAll, onRemap }: Props) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [reviewOnly, setReviewOnly] = useState(true);
  const { getIntersectingNodes } = useReactFlow();

  const toggle = useCallback((id: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const { rfNodes, rfEdges } = useMemo(() => {
    const { nodes, edges } = buildBoardGraph(wbs, cards, { collapsed, reviewOnly });
    const pos = layoutBoard(nodes, edges);
    const rfNodes: Node[] = nodes.map((n) => ({
      id: n.id,
      type: n.kind === "qty" ? "qty" : "hier",
      position: pos.get(n.id) ?? { x: 0, y: 0 },
      draggable: n.kind === "qty",
      data:
        n.kind === "qty"
          ? { item: n.item!, onConfirm }
          : { label: n.label, reviewCount: n.reviewCount, hasChildren: n.hasChildren, collapsed: collapsed.has(n.id), onToggle: toggle, isWp: n.isWp },
    }));
    const rfEdges: Edge[] = edges.map((e) => ({
      id: e.id, source: e.source, target: e.target, type: "default",
      style: { stroke: e.review ? "#d97706" : "#cbd5e1", strokeWidth: e.review ? 2 : 1.5 },
    }));
    return { rfNodes, rfEdges };
  }, [wbs, cards, collapsed, reviewOnly, onConfirm, toggle]);

  const onNodeDragStop = useCallback(
    (_e: MouseEvent | TouchEvent, node: Node) => {
      if (node.type !== "qty") return;
      const hits = getIntersectingNodes(node).filter((n) => (n.data as { isWp?: boolean }).isWp === true);
      if (hits.length === 0) return;
      const target = hits[0];
      const item = (node.data as { item: ReviewItem }).item;
      if (target.id !== item.ai_mapped_wp_id) {
        onRemap(item.id, target.id, (target.data as { label?: string }).label ?? "");
      }
    },
    [getIntersectingNodes, onRemap]
  );

  return (
    <div className="relative h-full w-full">
      <div className="absolute right-3 top-3 z-10 flex items-center gap-3 rounded-lg border border-border-soft bg-card/90 px-3 py-1.5 shadow-sm backdrop-blur">
        <span className="text-xs font-medium text-ink">검토만</span>
        <Switch checked={reviewOnly} onCheckedChange={setReviewOnly} />
        <button type="button" onClick={onConfirmHighConf} className="inline-flex items-center gap-1 rounded-md border border-mint bg-card px-2.5 py-1 text-[11px] font-semibold text-mint-text hover:bg-mint-light/40">
          <CheckCheck className="h-3.5 w-3.5" /> 0.8↑ 확정
        </button>
        <button type="button" onClick={onConfirmAll} className="inline-flex items-center gap-1 rounded-md bg-mint px-2.5 py-1 text-[11px] font-semibold text-white hover:opacity-90">
          <CheckCheck className="h-3.5 w-3.5" /> 모두 확정
        </button>
      </div>
      <ReactFlow nodes={rfNodes} edges={rfEdges} nodeTypes={nodeTypes} onNodeDragStop={onNodeDragStop} fitView proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function ReviewBoard(props: Props) {
  return (
    <ReactFlowProvider>
      <BoardInner {...props} />
    </ReactFlowProvider>
  );
}
