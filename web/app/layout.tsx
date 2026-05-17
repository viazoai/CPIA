import type { Metadata } from "next";
import "./globals.css";

/* 폰트는 globals.css 에서 jsdelivr CDN @import 로 로드한다.
 * next/font/google 은 빌드/dev 시 fonts.gstatic.com 으로 직접 fetch 시도하는데
 * homelab/사내 네트워크에서 차단되는 경우가 많아 사용하지 않는다. */

export const metadata: Metadata = {
  title: "CPIA · Construction Productivity Intelligence Agent",
  description: "AI Agent 기반 현장 생산성 분석 + 공기 최적화",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-surface font-sans text-ink antialiased">
        {children}
      </body>
    </html>
  );
}
