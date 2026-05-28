"use client";
/* 랜딩 → 슬라이드 발표 모드 셸.
 * 자식을 stack 으로 쌓아 translateY 로 한 화면씩 넘긴다.
 *
 * 입력:
 *   - children: 슬라이드 노드 배열 (각 <Slide>… 권장)
 * 인터랙션:
 *   - 휠 / Space / ↓ / PageDown / → → 다음
 *   - ↑ / PageUp / ← → 이전
 *   - Home / End → 처음 / 마지막
 *   - 우측 dot 클릭, 좌하단 prev·next, 우하단 카운터 노출
 *   - touch swipe (vertical) 지원
 *   - 슬라이드 전환 중에는 다음 입력 lock (700ms) — 연속 wheel 폭주 방지
 * 활성 슬라이드에는 data-active="true" 가 붙어 CSS keyframe 으로 entrance 트리거. */
import {
  Children,
  ReactNode,
  isValidElement,
  cloneElement,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ChevronUp, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  children: ReactNode;
}

const TRANSITION_MS = 700; // CSS transition duration 와 일치

export function PresentationShell({ children }: Props) {
  const slides = Children.toArray(children).filter(isValidElement);
  const total = slides.length;

  const [index, setIndex] = useState(0);
  const lockRef = useRef(false);

  const go = useCallback(
    (next: number) => {
      const clamped = Math.max(0, Math.min(total - 1, next));
      if (clamped === index || lockRef.current) return;
      lockRef.current = true;
      setIndex(clamped);
      window.setTimeout(() => {
        lockRef.current = false;
      }, TRANSITION_MS);
    },
    [index, total],
  );

  // wheel — vertical delta only, throttled via lockRef.
  // 슬라이드 내부에 스크롤 가능한 영역이 있으면 끝에 닿기 전까지는 슬라이드 전환을 보류한다.
  useEffect(() => {
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) < 20) return;
      const slideEl = (e.target as HTMLElement | null)?.closest(
        ".slide",
      ) as HTMLElement | null;
      if (slideEl) {
        const atTop = slideEl.scrollTop <= 1;
        const atBottom =
          slideEl.scrollTop + slideEl.clientHeight >= slideEl.scrollHeight - 1;
        const goingDown = e.deltaY > 0;
        // 내부 스크롤이 끝에 닿지 않았으면 그대로 통과 (브라우저가 슬라이드 내부 스크롤).
        if ((goingDown && !atBottom) || (!goingDown && !atTop)) {
          return;
        }
      }
      e.preventDefault();
      go(index + (e.deltaY > 0 ? 1 : -1));
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => window.removeEventListener("wheel", onWheel);
  }, [go, index]);

  // keyboard.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const fwd = ["ArrowDown", "ArrowRight", "PageDown", " ", "Spacebar"];
      const bwd = ["ArrowUp", "ArrowLeft", "PageUp"];
      if (fwd.includes(e.key)) {
        e.preventDefault();
        go(index + 1);
      } else if (bwd.includes(e.key)) {
        e.preventDefault();
        go(index - 1);
      } else if (e.key === "Home") {
        go(0);
      } else if (e.key === "End") {
        go(total - 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index, total]);

  // touch swipe — 수직 50px 이상.
  useEffect(() => {
    let startY = 0;
    let startX = 0;
    const onTouchStart = (e: TouchEvent) => {
      startY = e.touches[0].clientY;
      startX = e.touches[0].clientX;
    };
    const onTouchEnd = (e: TouchEvent) => {
      const dy = startY - e.changedTouches[0].clientY;
      const dx = startX - e.changedTouches[0].clientX;
      // 가로 swipe 가 더 강하면 무시.
      if (Math.abs(dx) > Math.abs(dy)) return;
      if (Math.abs(dy) < 50) return;
      go(index + (dy > 0 ? 1 : -1));
    };
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [go, index]);

  return (
    <div className="presentation-mode relative h-[calc(100vh-4rem)] overflow-hidden">
      {/* 상단 진행 바 */}
      <div className="absolute left-0 top-0 z-30 h-0.5 w-full bg-border-soft/50">
        <div
          className="h-full bg-gradient-to-r from-brand to-mint transition-all duration-700 ease-[cubic-bezier(0.65,0,0.35,1)]"
          style={{ width: `${((index + 1) / total) * 100}%` }}
        />
      </div>

      {/* 슬라이드 stack */}
      <div
        className="absolute inset-0 flex flex-col transition-transform duration-700 ease-[cubic-bezier(0.65,0,0.35,1)]"
        style={{ transform: `translateY(-${index * 100}%)` }}
      >
        {slides.map((child, i) => {
          // child 에 data-active 주입.
          const merged = cloneElement(child as any, {
            "data-active": i === index ? "true" : "false",
            "data-slide-index": i,
          });
          return (
            <div
              key={i}
              className="relative h-[calc(100vh-4rem)] w-full shrink-0"
              aria-hidden={i !== index}
            >
              {merged}
            </div>
          );
        })}
      </div>

      {/* 우측 dot 네비 */}
      <nav
        aria-label="Slide navigation"
        className="absolute right-5 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-3"
      >
        {slides.map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => go(i)}
            aria-label={`Slide ${i + 1}`}
            aria-current={i === index}
            className={cn(
              "group h-2 rounded-full transition-all duration-300",
              i === index
                ? "w-7 bg-brand"
                : "w-2 bg-ink-light/30 hover:bg-ink-light/60",
            )}
          />
        ))}
      </nav>

      {/* 좌하단 prev / next */}
      <div className="absolute bottom-5 left-5 z-30 flex flex-col gap-2">
        <button
          type="button"
          onClick={() => go(index - 1)}
          disabled={index === 0}
          aria-label="Previous slide"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-white/80 text-ink-mid backdrop-blur transition-all hover:bg-white hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
        >
          <ChevronUp className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={() => go(index + 1)}
          disabled={index === total - 1}
          aria-label="Next slide"
          className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-border bg-white/80 text-ink-mid backdrop-blur transition-all hover:bg-white hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
        >
          <ChevronDown className="h-4 w-4" />
        </button>
      </div>

      {/* 우하단 카운터 */}
      <div className="pointer-events-none absolute bottom-5 right-5 z-30 font-mono text-[11px] uppercase tracking-[0.12em] text-ink-light">
        <span className="text-ink">{String(index + 1).padStart(2, "0")}</span>
        <span> / {String(total).padStart(2, "0")}</span>
      </div>
    </div>
  );
}
