export function LandingFooter() {
  return (
    <footer className="border-t border-border-soft bg-card py-8">
      <div className="mx-auto flex max-w-wrap flex-col items-center justify-between gap-3 px-6 text-[12px] text-ink-light md:flex-row md:px-10">
        <span className="font-mono uppercase tracking-wider">
          © 2026 CPIA · Construction Productivity Intelligence Agent
        </span>
        <span className="font-mono uppercase tracking-wider">
          B_Track · v0.1 · PoC
        </span>
      </div>
    </footer>
  );
}
