// Client-safe bar/list filter helpers. transforms.ts 와 분리 — postgres (server only) 의존 회피.
// spec 2026-05-21-cpia-ui-4-fixes-design.md §④

/** value 150% 초과 제거 + value desc 상위 3 + asc 하위 7 = 최대 10개. */
export function filterAndPickBars<T extends { value: number }>(items: T[]): T[] {
  const cleaned = items.filter((b) => b.value <= 150);
  const sorted = [...cleaned].sort((a, b) => b.value - a.value);
  if (sorted.length <= 10) return sorted;
  const top3 = sorted.slice(0, 3);
  const bot7 = sorted.slice(-7);
  return [...top3, ...bot7];
}
