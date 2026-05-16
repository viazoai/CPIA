import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { PersonaToggle } from "./PersonaToggle";

export function TopBar() {
  return (
    <header className="sticky top-0 z-50 flex h-16 items-center justify-between border-b border-border bg-white/85 px-6 backdrop-blur-md md:px-10">
      <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-gradient-to-br from-lavender to-mint">
          <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        <span className="font-display text-base font-bold tracking-tight text-ink">
          CPIA
        </span>
        <Badge
          variant="outline"
          className="ml-2 gap-1 border-border bg-white px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-ink-mid"
        >
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-mint" />
          live · v0.1
        </Badge>
      </div>
      <PersonaToggle />
    </header>
  );
}
