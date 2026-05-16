"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Bot,
  ClipboardCheck,
  FileBarChart,
  LayoutDashboard,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { usePersona, isMenuVisible } from "@/lib/persona";
import { useUiStore } from "@/lib/ui-store";
import { cn } from "@/lib/utils";
import { PersonaToggle } from "./PersonaToggle";

const MENUS = [
  { key: "home",      label: "Home",          href: "/home",       icon: Home },
  { key: "tasks",     label: "Agent Tasks",   href: "/tasks",      icon: Bot },
  { key: "review",    label: "Human Review",  href: "/review",     icon: ClipboardCheck },
  { key: "reports",   label: "Report",        href: "/reports",    icon: FileBarChart },
  { key: "dashboard", label: "Dashboard",     href: "/dashboard",  icon: LayoutDashboard },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const persona = usePersona((s) => s.persona);
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);

  return (
    <aside
      className={cn(
        /* TopBar(h-16) 아래에 sticky 로 고정 — main 컨텐츠 높이에 끌려가지 않음.
         * 내부는 flex-col + nav 영역만 overflow scroll → footer(PersonaToggle) 항상 가시. */
        "sticky top-16 hidden h-[calc(100vh-4rem)] shrink-0 flex-col border-r border-border bg-white/60 backdrop-blur-sm transition-[width] duration-200 ease-out md:flex",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Header — label + toggle */}
      <div
        className={cn(
          "flex items-center pt-5 pb-2",
          collapsed ? "justify-center px-3" : "justify-between px-5"
        )}
      >
        {!collapsed && (
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-light opacity-60">
            Main Menu
          </span>
        )}
        <button
          type="button"
          onClick={toggle}
          aria-label={collapsed ? "사이드바 펼치기" : "사이드바 접기"}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-light transition-colors hover:bg-surface-soft hover:text-ink"
        >
          {collapsed ? (
            <ChevronsRight className="h-4 w-4" />
          ) : (
            <ChevronsLeft className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Nav — 메뉴가 많아지면 내부 스크롤, footer 는 항상 바닥 고정 */}
      <nav
        className={cn(
          "flex flex-1 flex-col gap-1 overflow-y-auto",
          collapsed ? "px-2" : "px-3"
        )}
      >
        {MENUS.filter((m) => isMenuVisible(persona, m.key)).map((m) => {
          const active = pathname === m.href || pathname?.startsWith(m.href + "/");
          const Icon = m.icon;
          return (
            <Link
              key={m.key}
              href={m.href}
              title={collapsed ? m.label : undefined}
              className={cn(
                "group flex items-center rounded-md text-sm transition-colors",
                collapsed
                  ? "h-10 w-12 justify-center"
                  : "gap-3 px-3 py-2.5",
                active
                  ? "bg-lavender-light text-lavender-text font-semibold"
                  : "text-ink-mid hover:bg-surface-soft"
              )}
            >
              <Icon
                className={cn("h-4 w-4 shrink-0")}
                strokeWidth={active ? 2.5 : 2}
              />
              {!collapsed && <span className="truncate">{m.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Footer — PersonaToggle + 버전 태그 */}
      <div
        className={cn(
          "mt-auto flex flex-col gap-3 border-t border-border-soft",
          collapsed ? "items-center px-2 py-3" : "px-4 py-4"
        )}
      >
        {!collapsed && (
          <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-ink-light opacity-60">
            View as
          </span>
        )}
        <PersonaToggle compact={collapsed} />
        {!collapsed && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-light/70">
            v0.1 · PoC · B_Track
          </span>
        )}
      </div>
    </aside>
  );
}
