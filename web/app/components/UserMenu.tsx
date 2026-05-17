"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, User, Settings, LogOut, BadgeCheck } from "lucide-react";
import { usePersona } from "@/lib/persona";
import { cn } from "@/lib/utils";

/* 페르소나별 mock 사용자 — 데모용 */
const USERS = {
  member: {
    name: "김 현장",
    role: "현장 PM · Hi-tech Div.",
    email: "kim.fld@cpia.demo",
    initials: "김",
    tone: "bg-mint-light text-mint-text",
  },
  manager: {
    name: "이 본부",
    role: "경영진 · Top Mgmt",
    email: "lee.exec@cpia.demo",
    initials: "이",
    tone: "bg-lavender-light text-lavender-text",
  },
} as const;

export function UserMenu() {
  const persona = usePersona((s) => s.persona);
  const user = USERS[persona];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-2.5 rounded-md py-1.5 pl-1.5 pr-2 transition-colors hover:bg-surface-soft",
          open && "bg-surface-soft"
        )}
      >
        <span
          className={cn(
            "inline-flex h-8 w-8 items-center justify-center rounded-full font-semibold text-sm",
            user.tone
          )}
        >
          {user.initials}
        </span>
        <span className="hidden text-left md:block">
          <span className="block text-sm font-semibold leading-tight text-ink">
            {user.name}
          </span>
          <span className="block text-[11px] leading-tight text-ink-light">
            {user.role.split(" · ")[0]}
          </span>
        </span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-ink-light transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-50 w-64 overflow-hidden rounded-card border border-border bg-card shadow-lg">
          {/* Header — full identity */}
          <div className="flex items-center gap-3 border-b border-border-soft px-4 py-3.5">
            <span
              className={cn(
                "inline-flex h-10 w-10 items-center justify-center rounded-full font-semibold",
                user.tone
              )}
            >
              {user.initials}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <span className="truncate text-sm font-semibold text-ink">{user.name}</span>
                <BadgeCheck className="h-3.5 w-3.5 shrink-0 text-lavender" />
              </div>
              <span className="block truncate text-xs text-ink-mid">{user.role}</span>
              <span className="mt-0.5 block truncate font-mono text-[10px] text-ink-light">
                {user.email}
              </span>
            </div>
          </div>

          {/* Menu items */}
          <nav className="flex flex-col py-1">
            <MenuItem icon={<User className="h-4 w-4" />} label="프로필" />
            <MenuItem icon={<Settings className="h-4 w-4" />} label="환경설정" />
          </nav>

          <div className="border-t border-border-soft py-1">
            <MenuItem
              icon={<LogOut className="h-4 w-4" />}
              label="로그아웃"
              tone="danger"
            />
          </div>
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  tone = "default",
}: {
  icon: React.ReactNode;
  label: string;
  tone?: "default" | "danger";
}) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2.5 px-4 py-2 text-sm transition-colors hover:bg-surface-soft",
        tone === "danger" ? "text-rose-text" : "text-ink-mid hover:text-ink"
      )}
    >
      {icon}
      {label}
    </button>
  );
}
