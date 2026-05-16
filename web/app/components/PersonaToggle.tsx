"use client";
import { Users, UserCog } from "lucide-react";
import { usePersona } from "@/lib/persona";
import { cn } from "@/lib/utils";

export function PersonaToggle() {
  const persona = usePersona((s) => s.persona);
  const setPersona = usePersona((s) => s.setPersona);

  return (
    <div className="inline-flex rounded-md border border-border bg-white p-0.5">
      <button
        type="button"
        onClick={() => setPersona("member")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "member"
            ? "bg-lavender text-white"
            : "text-ink-mid hover:text-ink"
        )}
      >
        <Users className="h-3.5 w-3.5" />
        구성원
      </button>
      <button
        type="button"
        onClick={() => setPersona("manager")}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[5px] px-3 py-1.5 text-xs font-semibold transition-colors",
          persona === "manager"
            ? "bg-lavender text-white"
            : "text-ink-mid hover:text-ink"
        )}
      >
        <UserCog className="h-3.5 w-3.5" />
        관리자
      </button>
    </div>
  );
}
