"use client";
import { useState, useMemo } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { WBSNode } from "@/lib/types";

interface WPOption {
  id: string;
  path: string;
}

interface Props {
  wbsRoot: WBSNode;
  currentWpId: string;
  onSelect: (wpId: string, path: string) => void;
}

function flattenWPs(node: WBSNode, ancestors: string[] = []): WPOption[] {
  const path = [...ancestors, node.name];
  if (node.type === "work_package") {
    return [{ id: node.id, path: path.join(" > ") }];
  }
  return (node.children || []).flatMap((c) => flattenWPs(c, path));
}

export function WPSearchCombobox({ wbsRoot, currentWpId, onSelect }: Props) {
  const allOptions = useMemo(() => flattenWPs(wbsRoot), [wbsRoot]);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!query.trim()) return allOptions;
    const q = query.toLowerCase();
    return allOptions.filter((o) => o.path.toLowerCase().includes(q));
  }, [allOptions, query]);

  return (
    <div className="relative">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-ink-light" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder="WP 이름 또는 코드로 검색 (예: 철근)"
          className="w-full rounded-md border border-border bg-white pl-8 pr-2 py-1.5 text-xs text-ink placeholder:text-ink-light focus:border-lavender focus:outline-none"
        />
      </div>
      {open && filtered.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-border-soft bg-white shadow-md">
          {filtered.slice(0, 12).map((o) => (
            <li
              key={o.id}
              onMouseDown={() => {
                onSelect(o.id, o.path);
                setQuery("");
                setOpen(false);
              }}
              className={cn(
                "cursor-pointer px-3 py-1.5 text-xs hover:bg-lavender-light/40",
                o.id === currentWpId && "bg-mint-light/50 font-semibold"
              )}
            >
              {o.path}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
