import { Brain, History, Lightbulb, Database } from "lucide-react";
import type { OptimizerOutput } from "@/lib/types";

/**
 * 진단·유사사례·권고·상세 4 섹션을 단일 박스 + 항목별 구분선.
 * 본문 텍스트는 모두 진단 디스크립션과 동일한 text-sm sans + leading-relaxed.
 */
export function OptimizerResult({ output }: { output: OptimizerOutput }) {
  return (
    <div className="h-full overflow-hidden rounded-card border border-border-soft bg-card shadow-xs">
      <Row icon={<Brain className="h-4 w-4" />} tone="brand" title="진단">
        <p className="text-sm text-ink-mid leading-relaxed whitespace-pre-line">
          {output.diagnosis || "진단 데이터 없음 (Optimizer 미실행 또는 cold_start)"}
        </p>
      </Row>
      <Row icon={<History className="h-4 w-4" />} tone="brand" title="유사 과거 사례" topBorder>
        {output.similar_cases?.length ? (
          <>
            {/* 2026-05-29 (2차): 회복 요약을 헤더 바로 밑(목록 위)으로 + 표시되는 3건 기준 + 평균회복 편입. */}
            {output.recovery_distribution_text ? (
              <div className="mb-2 rounded bg-surface-soft px-2 py-1 text-[12.5px] font-medium text-ink-mid">
                {output.recovery_distribution_text}
              </div>
            ) : null}
            <ul className="space-y-2">
              {output.similar_cases.slice(0, 3).map((c, i) => (
                <li key={i} className="text-sm text-ink-mid leading-relaxed">
                  <span className="font-semibold text-ink">{c.date}</span>
                  {c.condition ? `  [${c.condition}]` : ""}
                  {c.degraded ? (
                    <div className="mt-0.5 ml-1">저하: {c.degraded}</div>
                  ) : c.description ? (
                    <div className="mt-0.5 ml-1">{c.description}</div>
                  ) : null}
                  {c.recovered ? <div className="ml-1">회복: {c.recovered}</div> : null}
                  <div className="mt-0.5 ml-1 text-mint-text leading-relaxed">
                    → {c.recovery_days ? `${c.recovery_days}일 후 회복` : (c.outcome || "미회복")}
                  </div>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-ink-light leading-relaxed">유사 사례 없음 — 데이터 누적 후 갱신</p>
        )}
      </Row>
      <Row icon={<Lightbulb className="h-4 w-4" />} tone="sun" title="권고사항" topBorder>
        {output.recommendations?.length ? (
          <ul className="space-y-1.5 list-decimal list-inside marker:text-sun-text marker:font-semibold">
            {output.recommendations.map((r, i) => {
              if (typeof r === "string") {
                return <li key={i} className="text-sm text-ink-mid leading-relaxed">{r}</li>;
              }
              return (
                // 2026-05-29 (2차) 개조식 — sample optimizer-output-design.md 준용.
                // [키워드] 괄호 보이게(bold mint) + action 자연 줄바꿈(inline text) + 이유는 ← 흐린 텍스트.
                <li key={i} className="mb-2.5 text-sm leading-relaxed">
                  <div className="text-ink">
                    <span className="font-semibold text-mint-text">[{r.keyword}]</span>{" "}
                    <span>{r.action}</span>
                  </div>
                  {r.reason ? (
                    <div className="mt-0.5 ml-3 text-[12.5px] leading-relaxed text-ink-light">
                      ← {r.reason}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-ink-light leading-relaxed">권고 미산출 — cold_start</p>
        )}
      </Row>
      <Row icon={<Database className="h-4 w-4" />} tone="mint" title="상세 현황" topBorder>
        {output.details?.length ? (
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-sm leading-relaxed">
            {output.details.map((d, i) => (
              <div key={i} className="contents">
                <dt className="text-ink-light">{d.label}</dt>
                <dd className="font-semibold text-ink">{d.value || "—"}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-sm text-ink-light leading-relaxed">상세 데이터 없음</p>
        )}
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
        <span className={`text-sm font-semibold ${text}`}>
          {title}
        </span>
      </div>
      {children}
    </div>
  );
}
