import { Sun, Cloud, CloudRain, CloudSnow, MapPin, HardHat } from "lucide-react";
import type { HomeSiteInfo } from "@/lib/types";

interface Props {
  user: { name: string };
  site: HomeSiteInfo;
}

const WEATHER_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  sun: Sun,
  cloud: Cloud,
  "cloud-rain": CloudRain,
  "cloud-snow": CloudSnow,
};

const WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** "2025-09-25" → "2025. 09. 25 (목)" — 고정 시연 날짜라 UTC 기준으로 SSR/CSR 일치. */
function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const wd = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${y}. ${String(m).padStart(2, "0")}. ${String(d).padStart(2, "0")} (${WEEKDAY[wd]})`;
}

/**
 * 인삿말 + 현장 헤더 — 현장 항공사진 위 파란 그라데이션 밴드 (s.con 모바일 참고).
 *   배경: 현장 사진 + 상단 진한 네이비 → 하단 page-bg 로 밝아지는 블루 오버레이
 *   좌: 현장명(prominent) + 안전 인삿말 / 우: 위치 · 날짜 · 날씨
 */
export function HomeGreetingHeader({ user, site }: Props) {
  const Weather = WEATHER_ICON[site.weather.icon] ?? Sun;

  return (
    <div
      className="relative h-72 overflow-hidden text-white md:h-[22rem]"
      style={{
        background: [
          // 좌측 텍스트 가독성 스크림 — 좌측 진함 → 우측 투명(건물·로고 보존)
          "linear-gradient(90deg, rgba(7,15,38,0.64) 0%, rgba(7,15,38,0.30) 38%, rgba(7,15,38,0) 64%)",
          // 블루 오버레이 — 상단 진함 → 하단 page-bg(#f9fafc) 로 더 넓고 완만하게 밝아짐
          "linear-gradient(180deg, rgba(7,15,38,0.78) 0%, rgba(11,28,72,0.60) 20%, rgba(20,56,150,0.44) 42%, rgba(64,116,205,0.40) 62%, rgba(130,170,228,0.44) 82%, rgba(210,222,246,0.78) 93%, rgba(249,250,252,1) 100%)",
          // 현장 항공사진 (로고가 보이도록 위로 시프트)
          "url('/site-hero-m15x.jpg')",
        ].join(", "),
        backgroundSize: "cover, cover, cover",
        backgroundPosition: "center, center, 64% 58%",
      }}
    >
      <div className="relative mx-auto flex h-full w-full max-w-screen-2xl flex-col justify-end px-6 pb-10 md:px-10 md:pb-12">
        {/* 날짜 */}
        <span className="font-mono text-xs uppercase tracking-[0.14em] text-white/70">
          {formatDate(site.date)}
        </span>

        {/* 현장명 */}
        <h1 className="mt-2 font-display text-h2 text-white drop-shadow-sm">{site.name}</h1>

        {/* 위치 · 날씨 */}
        <div className="mt-2.5 flex items-center gap-3 text-white/85">
          <span className="inline-flex items-center gap-1.5 text-body-sm">
            <MapPin className="h-4 w-4 text-white/80" />
            {site.location ?? "—"}
          </span>
          <span className="h-3.5 w-px bg-white/25" />
          <span className="inline-flex items-center gap-1.5">
            <Weather className="h-4 w-4 text-amber-300" />
            <span className="text-body-sm">{site.weather.label}</span>
            <span className="font-display text-h6 tabular-nums text-white">{site.weather.temp_c}°</span>
          </span>
        </div>

        {/* 인삿말 */}
        <p className="mt-3 inline-flex items-center gap-1.5 text-body text-white/85">
          <HardHat className="h-4 w-4 text-amber-300" />
          <span className="font-semibold text-white">{user.name}님</span>, 오늘도 안전한 하루 되세요
        </p>
      </div>
    </div>
  );
}
