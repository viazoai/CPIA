import { Pause, UserCheck } from "lucide-react";

export function HilReviewStage() {
  return (
    <div className="relative my-6 flex flex-col items-center">
      <span aria-hidden className="h-8 w-px bg-gradient-to-b from-transparent via-white/15 to-amber-400/40" />

      <div
        className="relative w-full max-w-2xl rounded-xl border border-amber-400/30 bg-amber-400/[0.05] backdrop-blur-md p-5"
        style={{
          boxShadow:
            "0 0 60px -18px rgba(251,191,36,0.35), inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      >
        <div className="flex items-start gap-4">
          <span className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-amber-400/20 ring-1 ring-amber-400/40">
            <Pause className="h-5 w-5 text-amber-300" strokeWidth={2.5} fill="currentColor" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <UserCheck className="h-3.5 w-3.5 text-amber-300" strokeWidth={2.5} />
              <span className="font-mono text-xs uppercase tracking-wider text-amber-300 font-bold">
                HIL REVIEW · 사람 개입
              </span>
            </div>
            <div className="mt-1.5 font-display text-base font-bold tracking-tight text-white md:text-lg">
              확신도 낮은 매핑을 담당자가 검토·확정
            </div>
            <p className="mt-2 text-xs text-white/60 leading-relaxed md:text-sm">
              Mapper 출력 중 확신도가 낮은 항목만 Human Review 화면으로 전달 — 빠른 확인 후 Atomizer로 진행 (시연 1단계 단순화).
            </p>
          </div>
        </div>
      </div>

      <span aria-hidden className="h-8 w-px bg-gradient-to-b from-amber-400/40 via-white/15 to-transparent" />
    </div>
  );
}
