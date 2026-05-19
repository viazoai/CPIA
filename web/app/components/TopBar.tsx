import Link from "next/link";
import { Sparkles } from "lucide-react";
import { NotificationBell } from "./NotificationBell";
import { UserMenu } from "./UserMenu";

export function TopBar() {
  return (
    <header className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border bg-white/85 px-6 backdrop-blur-md md:px-10">
      {/* Brand — 클릭 시 랜딩으로 이동 */}
      <Link
        href="/"
        aria-label="CPIA 랜딩 페이지로 이동"
        className="flex items-center gap-3 rounded-md outline-none transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-brand/40"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-brand to-mint">
          <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-base font-bold tracking-tight text-ink">
            CPIA
          </span>
          <span className="hidden text-body-sm text-ink-mid sm:inline">
            Construction Productivity Intelligence Agent
          </span>
        </div>
      </Link>
      {/* Actions cluster — 알림 / 사용자 */}
      <div className="flex items-center gap-2">
        <NotificationBell />
        <UserMenu />
      </div>
    </header>
  );
}
