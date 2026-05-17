export default function LandingLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  /* 풀스크린 랜딩 — TopBar / Sidebar 없음. body 의 blob 은 그대로 노출. */
  return <div className="relative min-h-screen">{children}</div>;
}
