"use client";
import { useEffect, useState } from "react";

interface StatusHeaderProps {
  /** 마지막 동기화 시각 라벨 (예: "09:12") */
  lastUpdated: string;
}

export function StatusHeader({ lastUpdated }: StatusHeaderProps) {
  /* mock — 마지막 동기화 이후 흐른 초를 라이브 인상으로 카운트 */
  const [secs, setSecs] = useState(14);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => (s >= 59 ? 1 : s + 1)), 1000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="border-b border-border-soft pb-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 01 — Operations Console
          </span>
          <h1 className="mt-3 font-display text-h3 text-ink">
            CPIA 운영 현황
          </h1>
          <p className="mt-2 text-body-sm text-ink-mid">
            CPIA의 현재까지 진행한 작업 지표와 7개 Agent가 워크플로우 단계별 현황을 한눈에 확인합니다.
          </p>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 shadow-sm">
          <span className="relative flex h-2 w-2">
            <span className="absolute inset-0 inline-flex h-full w-full animate-ping rounded-full bg-mint opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-mint" />
          </span>
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-mid">
            LIVE · 마지막 동기화 {secs}s 전 ({lastUpdated})
          </span>
        </div>
      </div>
    </header>
  );
}
