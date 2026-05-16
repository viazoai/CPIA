import { Pause, UserCheck } from "lucide-react";

export function HilReviewStage() {
  return (
    <div className="relative my-4 flex flex-col items-center">
      <span aria-hidden className="h-6 w-px bg-border" />
      <div className="relative w-full max-w-xl rounded-card border-2 border-peach/50 bg-peach-light/40 p-4 shadow-xs">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-peach text-white">
            <Pause className="h-4 w-4" strokeWidth={2.5} fill="currentColor" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <UserCheck className="h-3.5 w-3.5 text-peach-text" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-widest text-peach-text font-bold">
                HIL REVIEW · 사람 개입
              </span>
            </div>
            <div className="mt-1 font-display text-base font-bold tracking-tight text-ink">
              확신도 낮은 매핑을 담당자가 검토·확정
            </div>
            <p className="mt-1 text-xs text-ink-mid">
              Mapper의 출력 중 확신도가 낮은 항목만 Human Review 화면으로 전달 — 빠른 확인 후 Atomizer로 진행 (시연 시연 1단계로 단순화).
            </p>
          </div>
        </div>
      </div>
      <span aria-hidden className="h-6 w-px bg-border" />
    </div>
  );
}
