// review 카드 물량 표시 포맷 (review 페이지 전용).
// 1000 이상: 소수점 절삭 + 천단위 콤마 (예 15743.3 -> "15,743", 4800 -> "4,800").
// 1000 미만: 원래 값 그대로 (예 573.3 -> "573.3", 138.98 -> "138.98") — 콤마 불필요.
export function formatReviewQuantity(q: number): string {
  if (!Number.isFinite(q)) return String(q);
  return q >= 1000 ? Math.trunc(q).toLocaleString("en-US") : String(q);
}
