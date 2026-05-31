"use client";
import { useEffect, useRef, useState } from "react";
import { Bell, AlertTriangle, CheckCircle2, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

type NotifTone = "warning" | "danger" | "info";

interface NotifItem {
  id: string;
  tone: NotifTone;
  title: string;
  body: string;
  time: string;
}

const MOCK_NOTIFS: NotifItem[] = [
  {
    id: "n1",
    tone: "warning",
    title: "Mapping 검토 3건 대기",
    body: "확신도 낮은 매핑이 누적되었습니다.",
    time: "방금 전",
  },
  {
    id: "n2",
    tone: "danger",
    title: "M15X Ph-3 공기 리스크 D-3",
    body: "골조 공정 진척률이 계획 대비 –12%.",
    time: "12분 전",
  },
  {
    id: "n3",
    tone: "info",
    title: "Daily 보고서 생성 완료",
    body: "2025-09-27 통합 진단 보고서가 준비되었습니다.",
    time: "1시간 전",
  },
];

const TONE_STYLE: Record<NotifTone, { wrap: string; icon: React.ReactNode }> = {
  warning: {
    wrap: "bg-sun-light text-sun-text",
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
  },
  danger: {
    wrap: "bg-rose-light text-rose-text",
    icon: <AlertTriangle className="h-3.5 w-3.5" />,
  },
  info: {
    wrap: "bg-brand-light text-brand-text",
    icon: <FileText className="h-3.5 w-3.5" />,
  },
};

export function NotificationBell() {
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

  const count = MOCK_NOTIFS.length;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`알림 ${count}건`}
        className={cn(
          /* dashboard.png 톤 — 작고 미니멀, border 없이 hover 시에만 배경 */
          "relative inline-flex h-9 w-9 items-center justify-center rounded-md text-ink-mid transition-colors hover:bg-surface-soft hover:text-ink",
          open && "bg-surface-soft text-ink"
        )}
      >
        <Bell className="h-[18px] w-[18px]" strokeWidth={1.75} />
        {count > 0 && (
          <span className="absolute right-1.5 top-1.5 inline-flex h-2 w-2 rounded-full bg-rose ring-2 ring-white" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-card border border-border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b border-border-soft px-4 py-3">
            <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
              Notifications
            </span>
            <button className="text-xs text-brand hover:underline" type="button">
              모두 읽음
            </button>
          </div>
          <ul className="max-h-[420px] divide-y divide-border-soft overflow-y-auto">
            {MOCK_NOTIFS.map((n) => {
              const t = TONE_STYLE[n.tone];
              return (
                <li
                  key={n.id}
                  className="flex gap-3 px-4 py-3 transition-colors hover:bg-surface-soft"
                >
                  <span
                    className={cn(
                      "mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                      t.wrap
                    )}
                  >
                    {t.icon}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium text-ink">{n.title}</span>
                      <span className="shrink-0 font-mono text-[10px] text-ink-light">
                        {n.time}
                      </span>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-ink-mid">{n.body}</p>
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="border-t border-border-soft bg-surface-soft px-4 py-2.5 text-center">
            <button className="text-xs text-brand hover:underline" type="button">
              전체 알림 보기
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
