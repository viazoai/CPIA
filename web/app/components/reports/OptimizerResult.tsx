import { Brain, History, Lightbulb, Database } from "lucide-react";
import type { OptimizerOutput } from "@/lib/types";

/**
 * 진단·유사사례·권고·상세 4 섹션을 단일 박스 안에 항목별 구분선으로 분리.
 * 외곽 카드 한 개 + 내부 row 사이 border-t.
 */
export function OptimizerResult({ output }: { output: OptimizerOutput }) {
  return (
    <div className="overflow-hidden rounded-card border border-border-soft bg-card shadow-xs">
      <Row icon={<Brain className="h-4 w-4" />} tone="brand" title="진단">
        <p className="text-sm text-ink-mid leading-relaxed">{output.diagnosis}</p>
      </Row>
      <Row icon={<History className="h-4 w-4" />} tone="brand" title="유사 과거 사례" topBorder>
        <ul className="space-y-1.5">
          {output.similar_cases.map((c, i) => (
            <li key={i} className="text-xs">
              <span className="font-mono font-semibold text-ink">{c.date}</span>{" "}
              · <span className="text-ink-mid">{c.description}</span>
              <div className="mt-0.5 ml-1 text-[11px] text-mint-text">→ {c.outcome}</div>
            </li>
          ))}
        </ul>
      </Row>
      <Row icon={<Lightbulb className="h-4 w-4" />} tone="sun" title="권고사항" topBorder>
        <ul className="space-y-1 list-decimal list-inside marker:text-sun-text marker:font-semibold">
          {output.recommendations.map((r, i) => (
            <li key={i} className="text-xs text-ink-mid">{r}</li>
          ))}
        </ul>
      </Row>
      <Row icon={<Database className="h-4 w-4" />} tone="mint" title="상세 현황" topBorder>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
          {output.details.map((d, i) => (
            <div key={i} className="contents">
              <dt className="text-ink-light">{d.label}</dt>
              <dd className="font-semibold text-ink">{d.value}</dd>
            </div>
          ))}
        </dl>
      </Row>
    </div>
  );
}

function Row({
  icon,
  tone,
  title,
  children,
  topBorder,
}: {
  icon: React.ReactNode;
  tone: "brand" | "sun" | "mint";
  title: string;
  children: React.ReactNode;
  topBorder?: boolean;
}) {
  const bg = { brand: "bg-brand-light", sun: "bg-sun-light", mint: "bg-mint-light" }[tone];
  const text = { brand: "text-brand-text", sun: "text-sun-text", mint: "text-mint-text" }[tone];
  return (
    <div className={`px-4 py-3 ${topBorder ? "border-t border-border-soft" : ""}`}>
      <div className="mb-2 flex items-center gap-2">
        <span className={`inline-flex h-6 w-6 items-center justify-center rounded-sm ${bg} ${text}`}>
          {icon}
        </span>
        <span className={`font-mono text-xs uppercase tracking-wider font-bold ${text}`}>
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}
