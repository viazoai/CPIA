"use client";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { HierBox } from "./HierBox";

export interface HierNodeData {
  label: string;
  reviewCount: number;
  hasChildren: boolean;
  collapsed: boolean;
  onToggle: (id: string) => void;
  [key: string]: unknown;
}

export type HierNodeType = Node<HierNodeData>;

export function HierNode({ id, data }: NodeProps<HierNodeType>) {
  return (
    <>
      <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
      <HierBox
        label={data.label}
        reviewCount={data.reviewCount}
        hasChildren={data.hasChildren}
        collapsed={data.collapsed}
        onToggle={() => data.onToggle(id)}
      />
      <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
    </>
  );
}
