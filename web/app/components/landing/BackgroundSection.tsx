import {
  Mail,
  FileSpreadsheet,
  AlertTriangle,
  RotateCw,
  Users,
  Bot,
  Archive,
  ArrowRight,
} from "lucide-react";

const PAINS = [
  {
    icon: Mail,
    title: "작업일보 수작업 취합",
    body: "BP 100개사 이메일·카카오톡·SNS로 분산 수신. 수기 복붙·집계에 담당자 1~3명 전일 투입.",
    tag: "Y-1 OBL 400h/월",
  },
  {
    icon: FileSpreadsheet,
    title: "보고서 작성 반복 소모",
    body: "Daily·Weekly·Monthly Report, S-Curve 등 동일 데이터를 매번 PPT·Excel에 수기 기입.",
    tag: "6개 현장 ~1,144h/월 (Activity 실측)",
  },
  {
    icon: AlertTriangle,
    title: "공기 지연 사후 인지",
    body: "PM 경험칙으로 판단. 주간 회의 후 이상 인지 시 이미 만회 불가 구간 진입.",
    tag: "지연 발생 후 대응",
  },
  {
    icon: RotateCw,
    title: "전현장 동일 구조 중복",
    body: "6개 현장에서 완전히 동일한 Middle Office 프로세스 반복. 구조적 해결 없이 개인 노력으로 대응 중.",
    tag: "복제 미실현 손실",
  },
];

interface OfficeLayer {
  badge: string;
  title: string;
  subtitle: string;
  role: string;
  items: string[];
  note: string;
  /** note 아래 작게 표시되는 보조 문구. 있으면 한 단계 작은 폰트 + 옅은 톤. */
  noteSub?: string;
  icon: typeof Users;
  /** Tailwind class 조합 — 헤더 배경·border·아이콘 톤 */
  tone: {
    badgeBg: string;       // 좌측 eyebrow 영역
    badgeText: string;
    iconBg: string;
    iconText: string;
    border: string;
    role: string;
    note: string;
    cardRing?: string;     // Middle Office 강조용
  };
  aiBadge?: boolean;
}

const LAYERS: OfficeLayer[] = [
  {
    badge: "Front Office",
    title: "현장 관리·커뮤니케이션",
    subtitle: "사람만 가능한 본질적 역할",
    role: "사람이 직접 수행하는 영역",
    items: [
      "발주처 협의·의사결정",
      "공정 문제 해결·현장 조치",
      "리스크 판단·Catch-up 실행",
      "협력사(BP) 관계 관리",
    ],
    note: "현장 인력 부족에 따른 확충 필요",
    icon: Users,
    tone: {
      badgeBg: "bg-mint-light",
      badgeText: "text-mint-text",
      iconBg: "bg-mint-light",
      iconText: "text-mint-text",
      border: "border-border",
      role: "text-mint-text",
      note: "text-center text-base font-semibold text-mint-text",
    },
  },
  {
    badge: "Middle Office",
    title: "데이터 집계·검증·보고",
    subtitle: "AI 로 대체 가능한 레이어 — CPIA 타겟",
    role: "★ CPIA 가 자동화하는 영역",
    items: [
      "작업일보 취합·정합성 검증",
      "공정률·생산성 보고서 작성",
      "공기 지연 리스크 집계·모니터링",
      "회의 자료 데이터 가공·포매팅",
    ],
    note: "Hi-tech 2,506h/월 소비",
    noteSub: "(현장 Activity 전수 조사 기준)",
    icon: Bot,
    tone: {
      badgeBg: "bg-brand-light",
      badgeText: "text-brand-text",
      iconBg: "bg-brand-light",
      iconText: "text-brand-text",
      border: "border-brand/30",
      role: "text-brand-text",
      note: "text-center text-base font-semibold text-brand-text",
      cardRing: "ring-2 ring-brand/40 shadow-md",
    },
    aiBadge: true,
  },
  {
    badge: "Back Office",
    title: "검토·정산·시스템",
    subtitle: "기존 운영 유지 영역",
    role: "현행 유지 — CPIA 범위 외",
    items: [
      "기성 정산·회계 처리",
      "퇴직공제 신고·기록",
      "ERP·PMIS 시스템 관리",
      "계약 문서 보관·관리",
    ],
    note: "현행 유지",
    icon: Archive,
    tone: {
      badgeBg: "bg-surface-soft",
      badgeText: "text-ink-mid",
      iconBg: "bg-surface-soft",
      iconText: "text-ink-mid",
      border: "border-border",
      role: "text-ink-mid",
      note: "text-center text-base font-semibold text-ink-mid",
    },
  },
];

export function BackgroundSection() {
  return (
    <section
      id="background"
      className="border-t border-border-soft bg-surface-soft/50 py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        {/* ── Header ── */}
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 01 — Background
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            현장 인력을 실행 중심으로 재배치
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            이 과제는 단순히 현장의 보고 업무를 줄이는 자동화가 아닙니다.
            <br />
            현장 엔지니어가 수행하는 업무 중{" "}
            <span className="font-semibold text-ink">
              AI로 대체 가능한 Middle Office 레이어를 제거
            </span>
            하고, 
            <br />
            그 인력을{" "}
            <span className="font-semibold text-ink">
              Front Office 본연의 역할(공정 판단 · 발주처 협상 · 리스크 실행)
            </span>
            로 재배치함으로써 <br />
            조직의 일하는 방식을 구조적으로 전환합니다.
          </p>
        </div>

        {/* ── 3-Layer Diagram ── */}
        <div className="mt-14 rounded-card-lg border border-border bg-card p-6 md:p-8">
          <div className="mb-6 text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
            Construction Site — 3-Layer Structure
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {LAYERS.map((l) => {
              const Icon = l.icon;
              return (
                <div
                  key={l.badge}
                  className={`relative flex flex-col rounded-card border ${l.tone.border} bg-card ${l.tone.cardRing ?? ""}`}
                >
                  {l.aiBadge && (
                    <span className="absolute -top-2 right-4 inline-flex items-center gap-1 rounded-full bg-brand px-2.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-white shadow-sm">
                      AI 대체
                    </span>
                  )}

                  {/* head */}
                  <div className="flex items-center gap-3 border-b border-border-soft px-5 py-4">
                    <span className={`inline-flex h-10 w-10 items-center justify-center rounded-md ${l.tone.iconBg} ${l.tone.iconText}`}>
                      <Icon className="h-5 w-5" />
                    </span>
                    <div className="min-w-0">
                      <div className={`inline-block rounded-sm ${l.tone.badgeBg} px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider ${l.tone.badgeText}`}>
                        {l.badge}
                      </div>
                      <div className="mt-1 font-display text-body font-semibold text-ink">
                        {l.title}
                      </div>
                    </div>
                  </div>

                  {/* body */}
                  <div className="flex flex-1 flex-col gap-3 px-5 py-4">
                    <div className={`text-[11px] font-semibold uppercase tracking-wider ${l.tone.role}`}>
                      {l.role}
                    </div>
                    <ul className="space-y-1.5 text-body-sm text-ink-mid">
                      {l.items.map((it) => (
                        <li key={it} className="flex gap-2">
                          <span className="mt-1 inline-block h-1 w-1 rounded-full bg-ink-light shrink-0" />
                          <span>{it}</span>
                        </li>
                      ))}
                    </ul>
                    <div className={`mt-auto pt-2 ${l.tone.note}`}>
                      {l.note}
                      {l.noteSub && (
                        <div className="mt-0.5 text-xs font-normal opacity-75">
                          {l.noteSub}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── Flow bar ── */}
          <div className="mt-6 grid grid-cols-[1fr_auto_1.2fr_auto_1fr] items-center gap-3 rounded-card border border-border-soft bg-surface-soft/60 p-4">
            <div className="text-center">
              <div className="font-display text-body-sm font-semibold text-ink">협력사 / 현장관리자</div>
              <div className="mt-0.5 text-xs text-ink-mid">Middle Office 인력 재배치</div>
            </div>
            <ArrowRight className="h-4 w-4 text-ink-light" />
            <div className="rounded-card border border-brand/40 bg-brand-light/60 px-3 py-2 text-center shadow-inner">
              <div className="font-display text-body-sm font-semibold text-ink line-through decoration-rose decoration-2">
                현장사무직 / 계약직
              </div>
              <div className="mt-0.5 text-xs text-brand-text">→ AI Agent로 대체, Front Office로 이동</div>
            </div>
            <ArrowRight className="h-4 w-4 text-ink-light" />
            <div className="text-center">
              <div className="font-display text-body-sm font-semibold text-ink">현장 PM · 본사</div>
              <div className="mt-0.5 text-xs text-ink-mid">의사결정 집중</div>
            </div>
          </div>
        </div>

        {/* ── Reframing takeaway ── */}
        <div className="mt-6 rounded-card-lg border border-brand/40 bg-gradient-to-br from-brand-light/70 to-mint-light/30 p-6 md:p-8">
          <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            Reframing — 왜 &quot;없애는 것&quot;이 아닌 &quot;재정립&quot;인가
          </div>
          <p className="mt-3 text-body text-ink">
            <span className="font-semibold">Middle Office 인력 = Agent 오케스트레이터</span>로
            업스킬링하여, Front Office 역할을 더 명확히 하고 조직 구조적 AX 를 실현합니다.
          </p>
          <p className="mt-2 text-body-sm text-ink-mid">
            &quot;없앤다&quot;는 프레이밍은 저항을 부르지만 —{" "}
            <span className="font-semibold text-ink">&quot;직접 AI 와 일하는 구조로 전환&quot;</span>은
            가능성을 엽니다.
          </p>
        </div>

        {/* ── Pain Points (Activity 실측) ── */}
        <div className="mt-14">
          <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-ink-light">
            Pain Points — 현장 Activity 전수 조사 데이터 기반
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {PAINS.map((p, i) => {
              const Icon = p.icon;
              return (
                <div
                  key={i}
                  className="flex flex-col rounded-card-lg border border-border bg-card p-4 transition-shadow hover:shadow-md"
                >
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-rose-light text-rose-text">
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-light">
                      Pain 0{i + 1}
                    </span>
                  </div>
                  <h3 className="mt-5 font-display text-h6 text-ink">{p.title}</h3>
                  <p className="mt-4 flex-1 text-body-sm text-ink-mid">{p.body}</p>
                  <div className="mt-6 inline-flex w-fit items-center rounded-full bg-rose-light px-2.5 py-0.5 text-[11px] font-medium text-rose-text">
                    {p.tag}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
