import { Clock4, UsersRound, CalendarClock, Gauge } from "lucide-react";

const KPIS = [
  {
    icon: Gauge,
    label: "검토 시간 최소화",
    value: "D+0",
    unit: "당일",
    body: "D+2~3일 후 보고 → 당일 보고",
  },
  {
    icon: CalendarClock,
    label: "공사 기간 단축",
    value: "3~7",
    unit: "일 / 현장별",
    body: "보고 가속 + D-14 탐지 + 만회 조기 착수",
  },
  {
    icon: Clock4,
    label: "업무 투입시간 절감",
    value: "2,155",
    unit: "h / 월",
    body: "2,506h → 351h · 대체율 86%",
  },
  {
    icon: UsersRound,
    label: "재배치 인력 확보",
    value: "15.4",
    unit: "명",
    body: "2,155h ÷ 140h/명 기준",
  },
];

const TEAM_USAGE = [
  { team: "Y-1 Ph-1 OBL",    pain: "작업일보 취합 (400h) + QSR (200h) + PSR (160h) + 주간회의 (80h)",            current: 967, after: 97, rate: 90, residual: "이상치 확인, 발주처 협의" },
  { team: "Indiana Fab HAC", pain: "CWP Forecast (96h) + Daily 취합 (32h) + Progress Report (64h) + 자재 예측 (70h)", current: 410, after: 82, rate: 80, residual: "EVMS 분석 검토" },
  { team: "P&T 3 증축",        pain: "작업일보 (88h) + W/M Report (100h) + 공정률 (45h) + 생산성 분석 (20h)",       current: 296, after: 41, rate: 85, residual: "발주처 승인 대응" },
  { team: "M15X OBL & PT7",  pain: "Weekly Progress (100h) + 공정계획 (60h) + History 분석 (31h)",                current: 286, after: 40, rate: 85, residual: "Critical Path 판단" },
  { team: "Y-1 Ph-1 IBL",    pain: "일일 집계 (48h) + 공정원가 관리 (40h) + PJT 현황 점검 (60h)",                  current: 288, after: 40, rate: 85, residual: "안전 관리 판단" },
  { team: "청주 M15X IBL",     pain: "생산성·공정률 관리 (75h) + Forecasting (20h) + Daily Report (24h)",          current: 259, after: 36, rate: 80, residual: "근로자 등급 판단" },
];

const REDEPLOY = [
  { site: "Y-1 Ph-1 OBL",    fte: "5.9", use: "Front Office 강화 (공정 판단·발주처 협의)" },
  { site: "Indiana Fab HAC", fte: "2.5", use: "해외 현장 Front 역량 보강" },
  { site: "P&T 3 증축",        fte: "1.8", use: "Hi-tech 신규 현장 투입" },
  { site: "M15X OBL & PT7",  fte: "1.7", use: "Hi-tech 신규 현장 투입" },
  { site: "Y-1 Ph-1 IBL",    fte: "1.8", use: "Hi-tech 신규 현장 투입" },
  { site: "청주 M15X IBL",     fte: "1.6", use: "Hi-tech 신규 현장 투입" },
];

const PATHS = [
  {
    no: "01",
    title: "보고 사이클 D+2~3일 → D+0",
    body: "보고 가속만으로 현장 1개당 공사 기간 단축 3~5일 직접 기여",
  },
  {
    no: "02",
    title: "D-14 선행 탐지",
    body: "지연의 50~70% 가 2주 전 탐지 시 예방 가능",
  },
  {
    no: "03",
    title: "자재 수급 선제 대응",
    body: "월 15~30일분 현장 손실 제거 (자재 부족 대기 월 5~10건 × 3일)",
  },
  {
    no: "04",
    title: "보고 해방 인력 → 공정 최적화",
    body: "보고 업무 해방 인력 재배치로 공정 품질 5~10% 간접 개선",
  },
];

/* Impact 슬라이드 — 1/3 (Header + KPI grid + 공사 기간 단축 4 경로) */
export function ImpactSection() {
  return (
    <section
      id="impact"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto w-full max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 03 — Impact
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            Hi-tech 현장을 최적화 하다
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            사업 내 전수 조사 결과 Activity 321개 데이터를 재구성하여 산출하였으며, 검토 시간, 공사 기간 단축, 업무시간 절감, 재배치 인원 확보를 제공하는 현장 최적화 Agent 입니다.
          </p>
        </div>

        {/* KPI grid */}
        <div className="mt-10 grid gap-4 md:grid-cols-2 xl:grid-cols-4" data-stagger>
          {KPIS.map((k) => {
            const Icon = k.icon;
            return (
              <div
                key={k.label}
                className="group relative overflow-hidden rounded-card-lg border border-border bg-card p-7 transition-shadow hover:shadow-md"
              >
                <span className="absolute right-5 top-5 inline-flex h-10 w-10 items-center justify-center rounded-md bg-brand-light text-brand-text">
                  <Icon className="h-5 w-5" />
                </span>
                <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
                  {k.label}
                </div>
                <div className="mt-4 flex items-baseline gap-1.5">
                  <span className="font-display text-h2 leading-none text-ink">
                    {k.value}
                  </span>
                  <span className="text-body text-ink-light">{k.unit}</span>
                </div>
                <p className="mt-3 text-body-sm text-ink-mid">{k.body}</p>
              </div>
            );
          })}
        </div>

        {/* 공사 기간 단축 4 경로 — KPI 바로 아래 */}
        <div className="mt-10">
          <h3 className="font-display text-h5 text-ink">
            공사 기간 단축으로 이어지는 4가지
          </h3>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            {PATHS.map((p) => (
              <div
                key={p.no}
                className="flex gap-4 rounded-card border border-border-soft bg-card p-5"
              >
                <span className="font-mono text-h5 leading-none text-brand">
                  {p.no}
                </span>
                <div>
                  <div className="font-semibold text-ink">{p.title}</div>
                  <p className="mt-1 text-body-sm text-ink-mid">{p.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

/* Impact 슬라이드 — 2/3 (업무 절감 시간 및 AI 대체율 — TEAM_USAGE table) */
export function ImpactWorkloadSection() {
  return (
    <section
      id="impact-workload"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto w-full max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 03 — Impact
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            업무 절감 시간 및 AI 대체율
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            6개 Hi-tech 현장 Activity 전수 조사 기준, 월간{" "}
            <span className="font-semibold text-ink">2,506h → 351h</span> ·
            평균 대체율 <span className="font-semibold text-ink">86%</span>.
          </p>
        </div>

        <div className="mt-10 overflow-x-auto rounded-card-lg border border-border bg-card">
          <table className="w-full text-body-sm">
            <thead>
              <tr className="border-b border-border bg-surface-soft/60 text-left">
                <th className="px-4 py-3 font-semibold text-ink-mid">현장 / 팀</th>
                <th className="px-4 py-3 font-semibold text-ink-mid">주요 Pain 업무</th>
                <th className="px-4 py-3 text-right font-semibold text-ink-mid whitespace-nowrap">현재 월간</th>
                <th className="px-4 py-3 text-right font-semibold text-ink-mid whitespace-nowrap">AI 전환 후</th>
                <th className="px-4 py-3 font-semibold text-ink-mid whitespace-nowrap">대체율</th>
                <th className="px-4 py-3 font-semibold text-ink-mid whitespace-nowrap">잔여 업무</th>
              </tr>
            </thead>
            <tbody>
              {TEAM_USAGE.map((row) => (
                <tr key={row.team} className="border-b border-border-soft last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-semibold text-ink">{row.team}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-mid">{row.pain}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums text-rose-text">{row.current.toLocaleString()}h</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums text-mint-text">~{row.after}h</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="w-9 font-mono font-semibold text-brand-text">{row.rate}%</span>
                      <div className="h-1.5 w-20 rounded-full bg-surface-soft">
                        <div className="h-full rounded-full bg-brand" style={{ width: `${row.rate}%` }} />
                      </div>
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-ink-light">{row.residual}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border bg-brand-light/40 font-semibold text-ink">
                <td colSpan={2} className="px-4 py-3">합계</td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums">2,506h/월</td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums">~351h/월</td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-brand-text">86%</td>
                <td className="whitespace-nowrap px-4 py-3">절감 2,155h/월</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>
  );
}

/* Impact 슬라이드 — 3/3 (인력 재배치 효과 — REDEPLOY table + 예산 절감 + FTE 각주) */
export function ImpactRedeploySection() {
  return (
    <section
      id="impact-redeploy"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto w-full max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 03 — Impact
          </span>
          <h2 className="mt-3 flex items-center gap-2.5 font-display text-h3 text-ink">
            인력 재배치 효과
            <span className="inline-flex items-center rounded-full bg-brand-light px-3 py-1 text-sm font-semibold uppercase tracking-[0.12em] text-brand-text">
              핵심 임팩트
            </span>
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            절감된 업무 시간을{" "}
            <span className="font-semibold text-ink">FTE 15.4명</span> 으로 환산 — 신규 충원 없이 Front Office 인력 확보.
          </p>
        </div>

        <div className="mt-10 overflow-x-auto rounded-card-lg border border-border bg-card">
          <table className="w-full text-body-sm">
            <thead>
              <tr className="border-b border-border bg-surface-soft/60 text-left">
                <th className="px-4 py-3 font-semibold text-ink-mid">현장</th>
                <th className="px-4 py-3 text-right font-semibold text-ink-mid whitespace-nowrap">절감 FTE</th>
                <th className="px-4 py-3 font-semibold text-ink-mid">재배치 활용 방향</th>
              </tr>
            </thead>
            <tbody>
              {REDEPLOY.map((row) => (
                <tr key={row.site} className="border-b border-border-soft last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-semibold text-ink">{row.site}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums text-ink">{row.fte}명</td>
                  <td className="px-4 py-3 text-ink-mid">{row.use}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-border bg-brand-light/40 font-semibold text-ink">
                <td className="whitespace-nowrap px-4 py-3">합계</td>
                <td className="whitespace-nowrap px-4 py-3 text-right font-mono tabular-nums">FTE 15.4명</td>
                <td className="px-4 py-3">신규 충원 없이 Front Office 배치 인원 확보</td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* 신규 채용 예산 절감 요약 */}
        <div className="mt-4 rounded-card border border-brand/30 bg-brand-light/30 p-5">
          <div className="text-body-sm text-ink">
            <span className="font-semibold">연간 신규 채용 예산 절감 — </span>
            재배치 가능 인원 15.4 명 × 인당 채용 비용 1.5 억 원 (평균 연봉 + 채용·교육·복리후생 등 부대 비용) ={" "}
            <strong className="text-brand-text">약 23 억 원 / 연간</strong>
          </div>
        </div>

        {/* FTE 개념 각주 */}
        <p className="mt-3 text-xs text-ink-light">
          ※ FTE (Full-Time Equivalent, 전일제 환산 인원) — 절감된 업무 시간을 1인 월 표준 근무 140h 로 나눠 환산한 인력 규모
        </p>
      </div>
    </section>
  );
}
