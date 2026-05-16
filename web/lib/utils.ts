import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn 표준 헬퍼 — clsx 로 조건부 className 결합 후 tailwind-merge 로 충돌 정리.
 * 예: cn("p-4 bg-white", isActive && "bg-mint-light", className)
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
