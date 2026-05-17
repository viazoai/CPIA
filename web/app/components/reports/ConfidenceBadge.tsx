import { cn } from "@/lib/utils";

interface Props {
  sampleSize: number;
}

const TONE_OK   = "bg-surface-soft text-ink-mid";
const TONE_LOW  = "bg-sun-light text-sun-text";

export function ConfidenceBadge({ sampleSize }: Props) {
  const low = sampleSize < 20;
  /* dot fill 비율 — N≥50 full, 30~ 5, 20~ 4, 10~ 3, 그 아래 2 */
  const filled =
    sampleSize >= 50 ? 6 :
    sampleSize >= 30 ? 5 :
    sampleSize >= 20 ? 4 :
    sampleSize >= 10 ? 3 : 2;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full px-2.5 py-1",
        low ? TONE_LOW : TONE_OK,
      )}
    >
      <span className="flex gap-0.5" aria-hidden>
        {Array.from({ length: 6 }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              i < filled
                ? low ? "bg-sun" : "bg-brand"
                : "bg-border",
            )}
          />
        ))}
      </span>
      <span className="font-mono text-[10px] font-medium uppercase tracking-wider">
        N={sampleSize} 유사 케이스
      </span>
    </span>
  );
}
