/* 풀스크린 랜딩 (슬라이드 발표 모드) — 페이지 전체 스크롤 잠금. */
export default function LandingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="relative h-screen overflow-hidden">
      {children}
    </div>
  );
}
