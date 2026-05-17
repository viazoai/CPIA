import { Mail, FileSpreadsheet, AlertTriangle, RotateCw } from "lucide-react";

const PAINS = [
  {
    icon: Mail,
    title: "BP 100개사 분산 수신",
    body: "이메일·카카오톡·SNS 채널로 작업일보가 흩어져 들어와 담당자 1~3명이 전일 복붙·집계에 매달립니다.",
  },
  {
    icon: FileSpreadsheet,
    title: "PPT·Excel 수기 보고",
    body: "Daily·Weekly·Monthly Report, S-Curve 가 모두 동일 데이터인데도 매번 새로 손작업. 6개 현장 ~1,144h/월 소모.",
  },
  {
    icon: AlertTriangle,
    title: "사후 인지 — 만회 불가",
    body: "PM 경험칙으로 판단하고 주간 회의 후 이상이 잡힐 때면 이미 만회 가능 구간을 지난 상태입니다.",
  },
  {
    icon: RotateCw,
    title: "구조 없는 6개 현장 반복",
    body: "동일한 Middle Office 프로세스가 6개 현장에서 그대로 반복되며, 개인 노력에 기대 운영되고 있습니다.",
  },
];

export function BackgroundSection() {
  return (
    <section
      id="background"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 01 — Background
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            현장의 일을 재정의합니다.
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            이 과제는 단순히 현장의 보고 업무를 줄이는 자동화가 아닙니다.
            현장 엔지니어가 수행하는 업무 중{" "}
            <span className="font-semibold text-ink">
              AI로 대체 가능한 Middle Office 레이어를 제거
            </span>
            하고, 그 인력을{" "}
            <span className="font-semibold text-ink">
              Front Office 본연의 역할(공정 판단 · 발주처 협상 · 리스크 실행)
            </span>
            로 재배치함으로써 조직의 일하는 방식을 구조적으로 전환합니다.
          </p>
        </div>

        <div className="mt-14 grid gap-4 md:grid-cols-2">
          {PAINS.map((p, i) => {
            const Icon = p.icon;
            return (
              <div
                key={i}
                className="rounded-card-lg border border-border bg-card p-6 transition-shadow hover:shadow-md"
              >
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-rose-light text-rose-text">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="font-mono text-[11px] uppercase tracking-wider text-ink-light">
                    Pain 0{i + 1}
                  </span>
                </div>
                <h3 className="mt-4 font-display text-h5 text-ink">{p.title}</h3>
                <p className="mt-2 text-body-sm text-ink-mid">{p.body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
