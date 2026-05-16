"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Home, Bot, ClipboardCheck, FileBarChart, LayoutDashboard } from "lucide-react";
import { usePersona, isMenuVisible } from "@/lib/persona";
import { cn } from "@/lib/utils";

const MENUS = [
  { key: "home",      label: "Home",          href: "/",           icon: Home },
  { key: "tasks",     label: "Agent Tasks",   href: "/tasks",      icon: Bot },
  { key: "review",    label: "Human Review",  href: "/review",     icon: ClipboardCheck },
  { key: "reports",   label: "Report",        href: "/reports",    icon: FileBarChart },
  { key: "dashboard", label: "Dashboard",     href: "/dashboard",  icon: LayoutDashboard },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const persona = usePersona((s) => s.persona);

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border bg-white/60 backdrop-blur-sm">
      <div className="px-5 py-6">
        <span className="font-mono text-xs uppercase tracking-wider text-ink-light">
          Navigation
        </span>
      </div>
      <nav className="flex flex-col gap-1 px-3">
        {MENUS.filter((m) => isMenuVisible(persona, m.key)).map((m) => {
          const active = pathname === m.href || (m.href !== "/" && pathname?.startsWith(m.href));
          const Icon = m.icon;
          return (
            <Link
              key={m.key}
              href={m.href}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2.5 text-sm transition-colors",
                active
                  ? "bg-lavender-light text-lavender-text font-semibold"
                  : "text-ink-mid hover:bg-surface-soft"
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={active ? 2.5 : 2} />
              {m.label}
              {m.key === "dashboard" && persona === "manager" && (
                <span className="ml-auto rounded-sm bg-lavender px-1.5 py-0.5 text-[11px] uppercase tracking-wider text-white">
                  Mgmt
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto px-5 py-4 text-xs font-mono uppercase tracking-wider text-ink-light/70">
        v0.1 · PoC · B_Track
      </div>
    </aside>
  );
}
