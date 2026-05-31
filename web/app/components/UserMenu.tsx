"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronDown, User, Settings, LogOut, BadgeCheck, RotateCcw, Loader2 } from "lucide-react";
import { usePersona } from "@/lib/persona";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useSimStore } from "@/lib/sim-store";

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
    tone: "bg-brand-light text-brand-text",
  },
} as const;

// NEXT_PUBLIC_DEMO_RESET=1 일 때만 "시연 데이터 초기화" 노출.
const DEMO_RESET_ENABLED = process.env.NEXT_PUBLIC_DEMO_RESET === "1";

export function UserMenu() {
  const persona = usePersona((s) => s.persona);
  const user = USERS[persona];
  const [open, setOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const clearSimulation = useSimStore((s) => s.clearSimulation);

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

  const handleReset = async () => {
    setResetting(true);
    try {
      const res = await fetch("/api/upload/reset", { method: "DELETE" });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "초기화 실패");

      // 업로드 디렉토리뿐 아니라 진행 중인 H1 시뮬 상태(localStorage)도 함께 비움.
      clearSimulation();

      const failed: { path: string; error: string }[] = data.failed ?? [];
      const baseMsg = `폴더 ${data.deletedFolders}개, 파일 ${data.deletedFiles}개 삭제`;

      if (failed.length === 0) {
        toast.success(`시연 데이터 초기화 완료 — ${baseMsg}`);
      } else {
        // 부분 실패 — 보통 5535(uid 1001) ↔ 5537(uid 1000) 권한 차이 케이스.
        toast.warning(
          `시연 데이터 부분 초기화 — ${baseMsg}. 권한 부족 ${failed.length}개: ${failed
            .map((f) => f.path)
            .join(", ")}`,
          { duration: 8000 },
        );
      }
      setResetOpen(false);
    } catch (e: any) {
      toast.error(`초기화 실패: ${e?.message ?? "unknown"}`);
    } finally {
      setResetting(false);
    }
  };

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
                <BadgeCheck className="h-3.5 w-3.5 shrink-0 text-brand" />
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

          {DEMO_RESET_ENABLED && (
            <div className="border-t border-border-soft py-1">
              <MenuItem
                icon={<RotateCcw className="h-4 w-4" />}
                label="시연 데이터 초기화"
                onClick={() => {
                  setOpen(false);
                  setResetOpen(true);
                }}
              />
            </div>
          )}

          <div className="border-t border-border-soft py-1">
            <MenuItem
              icon={<LogOut className="h-4 w-4" />}
              label="로그아웃"
              tone="danger"
            />
          </div>
        </div>
      )}

      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>시연 데이터를 초기화할까요?</DialogTitle>
            <DialogDescription>
              <code className="rounded bg-surface-soft px-1.5 py-0.5 font-mono text-xs">data/upload/</code>{" "}
              하위의 모든 업로드 폴더와 파일이 삭제됩니다. 이 작업은 되돌릴 수 없습니다.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setResetOpen(false)}
              disabled={resetting}
            >
              취소
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleReset}
              disabled={resetting}
              className="gap-1.5"
            >
              {resetting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
              초기화
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MenuItem({
  icon,
  label,
  tone = "default",
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  tone?: "default" | "danger";
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
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
