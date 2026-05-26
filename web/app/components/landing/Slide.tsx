/* 슬라이드 한 장 — PresentationShell 자식.
 * 셸이 data-active="true|false" 와 data-slide-index 를 주입하므로 forward 한다.
 * 콘텐츠가 viewport 보다 크면 내부에서 overflow-y-auto 로 흡수. */
import { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface SlideProps {
  children: ReactNode;
  className?: string;
  /** 아래 두 prop 은 PresentationShell.cloneElement 가 주입 */
  ["data-active"]?: "true" | "false";
  ["data-slide-index"]?: number;
}

export function Slide({
  children,
  className,
  "data-active": active,
  "data-slide-index": idx,
}: SlideProps) {
  return (
    <section
      data-active={active}
      data-slide-index={idx}
      className={cn(
        "slide group relative h-full w-full overflow-y-auto overflow-x-hidden",
        className,
      )}
    >
      {children}
    </section>
  );
}
