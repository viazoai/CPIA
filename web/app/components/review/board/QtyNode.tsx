"use client";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { QtyCard } from "./QtyCard";
import type { ReviewItem } from "@/lib/types";

export interface QtyNodeData {
  item: ReviewItem;
  onConfirm: (id: string) => void;
  [key: string]: unknown;
}

export type QtyNodeType = Node<QtyNodeData>;

export function QtyNode({ data }: NodeProps<QtyNodeType>) {
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <QtyCard item={data.item} onConfirm={data.onConfirm} />
    </>
  );
}
