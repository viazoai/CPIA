import { MapPin } from "lucide-react";

interface HomeHeaderProps {
  siteName: string;
  dateLabel: string;
}

export function HomeHeader({ siteName, dateLabel }: HomeHeaderProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-ink-light">
        <MapPin className="h-3.5 w-3.5" />
        <span className="font-mono text-xs uppercase tracking-wider">{dateLabel}</span>
      </div>
      <h1 className="font-display text-h3 font-bold text-ink">{siteName}</h1>
      <p className="text-body-sm text-ink-mid">오늘도 안전한 하루 되세요</p>
    </div>
  );
}
