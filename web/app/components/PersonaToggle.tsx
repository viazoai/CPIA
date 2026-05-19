"use client";
import { Users, UserCog } from "lucide-react";
import { usePersona } from "@/lib/persona";
import { cn } from "@/lib/utils";

interface PersonaToggleProps {
  /** Rail 모드(축소 사이드바) — 단일 아이콘 버튼으로 표시 + 클릭 시 즉시 전환 */
  compact?: boolean;
}

export function PersonaToggle({ compact = false }: PersonaToggleProps) {
  const persona = usePersona((s) => s.persona);
  const setPersona = usePersona((s) => s.setPersona);
  const toggle = usePersona((s) => s.toggle);

  if (compact) {
    const isMgr = persona === "manager";
    return (
      <button
        type="button"
        onClick={toggle}
        title={isMgr ? "관리자 → 구성원 전환" : "구성원 → 관리자 전환"}
        aria-label={isMgr ? "관리자 모드 (클릭 전환)" : "구성원 모드 (클릭 전환)"}
        className={cn(
          "inline-flex h-10 w-12 items-center justify-center rounded-md border transition-colors",
          isMgr
            ? "border-brand bg-brand text-white hover:bg-brand-text"
            : "border-border bg-surface-soft text-ink hover:bg-card hover:text-brand-text"
        )}
      >
        {isMgr ? <UserCog className="h-4 w-4" /> : <Users className="h-4 w-4" />}
      </button>
    );
  }

  return (
    <div className="inline-flex w-full rounded-md border border-border bg-surface-soft p-0.5">
      <button
        type="button"
        onClick={() => setPersona("member")}
        className={cn(
          "inline-flex flex-1 items-center justify-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "member"
            ? "bg-brand text-white shadow-sm"
            : "text-ink hover:text-brand-text"
        )}
      >
        <Users className="h-3.5 w-3.5" />
        구성원
      </button>
      <button
        type="button"
        onClick={() => setPersona("manager")}
        className={cn(
          "inline-flex flex-1 items-center justify-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "manager"
            ? "bg-brand text-white shadow-sm"
            : "text-ink hover:text-brand-text"
        )}
      >
        <UserCog className="h-3.5 w-3.5" />
        관리자
      </button>
    </div>
  );
}
