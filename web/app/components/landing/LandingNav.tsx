"use client";
import Link from "next/link";
import { Sparkles, ArrowRight } from "lucide-react";

export function LandingNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/60 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-wrap items-center justify-between px-6 md:px-10">
        {/* Brand — TopBar 와 동일 배치 (CPIA + 풀네임 baseline 정렬) */}
        <Link href="/" className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-brand to-mint">
            <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-base font-bold tracking-tight text-ink">
              CPIA
            </span>
            <span className="hidden text-body-sm text-ink-mid sm:inline">
              Construction Productivity Intelligence Agent
            </span>
          </div>
        </Link>

        {/* CTA */}
        <Link
          href="/home"
          className="group inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-body-sm font-medium text-white transition-colors hover:bg-ink-mid"
        >
          Get Started
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </header>
  );
}
