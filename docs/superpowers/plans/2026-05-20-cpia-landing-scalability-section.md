# CPIA 랜딩 § 04 Scalability 재구성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 랜딩페이지 마지막 섹션을 시간축 4-Horizon 카드에서 확장축 3-Axis grid 로 재구성. 메시지를 "상품화 로드맵" → "확장성 설명" 으로 전환.

**Architecture:** 단일 React 컴포넌트 (`ScalabilitySection.tsx`) 데이터 배열·렌더링·카피 수정. anchor id `roadmap` 유지하여 헤더 메뉴 호환. 외부 의존성·다른 컴포넌트 변경 없음.

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS (커스텀 디자인 토큰), lucide-react

**Spec:** `docs/superpowers/specs/2026-05-20-cpia-landing-scalability-section-design.md`

---

## File Structure

- 수정: `web/app/components/landing/ScalabilitySection.tsx` — 단일 파일 전체 재작성 (현재 112 줄 → 약 105 줄)

---

## Task 1: ScalabilitySection.tsx 전체 교체

**Files:**
- Modify: `web/app/components/landing/ScalabilitySection.tsx` (전체 교체)

- [ ] **Step 1: 새 파일 내용 적용**

`web/app/components/landing/ScalabilitySection.tsx` 의 전체 내용을 아래로 교체:

```tsx
import { Cpu, Globe, Layers } from "lucide-react";

const AXES = [
  {
    icon: Cpu,
    axis: "AXIS 01",
    category: "FOUNDATION",
    title: "LangGraph 기반 — 쉽게 교체할 수 있도록 설계",
    body:
      "7개 Agent 가 독립 모듈로 구성되어, 현장 특성에 맞춰 일부 노드만 교체하면 동작. 새 현장·새 영역으로 옮길 때 코어 재학습 없이 빠르게 적용할 수 있도록 LangGraph 기술로 설계.",
    target: "노드 교체 only · 코어 재학습 불요",
    active: true,
  },
  {
    icon: Globe,
    axis: "AXIS 02",
    category: "HORIZONTAL SCALE-OUT",
    title: "Hi-tech 6개 → SK ecosystem 전체",
    body:
      "Hi-tech 사업부 6개 현장 내재화 후, AI Solution·글로벌 사업부로 동일 LangGraph 베이스 확산. 발주처 포맷·언어 모듈만 교체하여 신규 현장 적용.",
    target: "월 4,200h+ 통합 절감 (사업부 누적)",
  },
  {
    icon: Layers,
    axis: "AXIS 03",
    category: "MPRS DOMAIN EXPANSION",
    title: "P-Construction → R-Engineering · P-Procurement · M / PM",
    body:
      "현재 P-Construction 한정. 동일 패턴으로 R-Engineering (VE·Clash Detection·예상공기 검토), P-Procurement (자재 수급 예측), M / PM 까지 확장하여 전 EPC 단계 공기 단축에 기여.",
    target: "예상공기 검토시간 50% 절감 (Hi-tech 정보화 과제 요청 기준)",
  },
];

export function ScalabilitySection() {
  return (
    <section
      id="roadmap"
      className="border-t border-border-soft bg-card py-24 md:py-32"
    >
      <div className="mx-auto max-w-wrap px-6 md:px-10">
        <div className="max-w-3xl">
          <span className="text-[11px] font-medium uppercase tracking-[0.12em] text-brand-text">
            / 04 — Scalability · 확장성
          </span>
          <h2 className="mt-3 font-display text-h3 text-ink">
            하나의 현장 패턴이, 다른 현장·다른 영역의 출발점이 된다
          </h2>
          <p className="mt-6 text-body text-ink-mid">
            LangGraph 기반 노드 모듈 구조로 — 현장 다양성과 MPRS 전 영역을 같은 베이스에서 흡수. Hi-tech P-Construction 의 학습을 SK ecosystem 전체로 전이.
          </p>
        </div>

        <ol className="mt-14 grid gap-4 md:grid-cols-3">
          {AXES.map((a, i) => {
            const Icon = a.icon;
            return (
              <li
                key={i}
                className={`relative rounded-card-lg border p-6 transition-all ${
                  a.active
                    ? "border-brand bg-gradient-to-br from-brand-light/60 via-card to-card shadow-md"
                    : "border-border-soft bg-surface-soft/40"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-flex h-9 w-9 items-center justify-center rounded-md ${
                      a.active ? "bg-brand text-white" : "bg-card text-ink-mid"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                  </span>
                  <span
                    className={`text-[11px] font-medium uppercase tracking-[0.12em] ${
                      a.active ? "text-brand-text" : "text-ink-light"
                    }`}
                  >
                    {a.axis}
                  </span>
                </div>
                <div className="mt-5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-light">
                  {a.category}
                </div>
                <h3 className="mt-2 font-display text-h6 text-ink">{a.title}</h3>
                <p className="mt-3 text-body-sm text-ink-mid">{a.body}</p>
                <div className="mt-5 border-t border-border-soft pt-4">
                  <span className="text-[11px] font-medium uppercase tracking-wider text-ink-light">
                    Target
                  </span>
                  <div
                    className={`mt-0.5 font-display text-base font-semibold ${
                      a.active ? "text-brand-text" : "text-ink"
                    }`}
                  >
                    {a.target}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: HMR 자동 반영 확인**

`npm run dev` 가 5536 에서 떠 있는 상태. 파일 저장 즉시 Next.js HMR 이 변경을 잡아냄. 브라우저에서 `http://localhost:5536/#roadmap` 새로고침 (Ctrl+Shift+R).

확인할 것:
- 섹션 라벨이 "Roadmap" 에서 **"Scalability · 확장성"** 으로 바뀌었는지
- 카드 4개 → **3개**, 첫 번째 카드가 강조 (gradient) 되어 있고 LangGraph 아이콘인지
- 카드 순서: LangGraph → 현장 수평 → MPRS 영역
- 각 카드의 axis 라벨 (AXIS 01/02/03), category (FOUNDATION/HORIZONTAL SCALE-OUT/MPRS DOMAIN EXPANSION), title, body, target 이 spec 과 일치
- xl viewport 에서 grid 가 3 columns 로 균등 배치되는지 (md 이상 3-col)

- [ ] **Step 3: TypeScript 빌드 검증**

```bash
cd /home/ubuntu/cpia/web && npm run build 2>&1 | tail -30
```

Expected:
- `✓ Compiled successfully` 또는 동등 메시지
- 에러 없음. lucide-react import (`Cpu, Globe, Layers`) 모두 존재해야 정상 빌드.
- 미사용 import 경고 없음 (기존의 `Building2`, `Package` 가 import 에서 빠졌는지 자동 확인됨).

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/cpia
git add web/app/components/landing/ScalabilitySection.tsx docs/superpowers/specs/2026-05-20-cpia-landing-scalability-section-design.md docs/superpowers/plans/2026-05-20-cpia-landing-scalability-section.md
git commit -m "$(cat <<'EOF'
feat(B): 랜딩 § 04 Roadmap → Scalability 재구성

- 시간축 4-Horizon 카드 → 확장축 3-Axis grid 로 전환
- 메시지: '상품화 로드맵' → 'Agent 확장성 설명'
- 카드 순서 (스케일 small → large):
  · AXIS 01 LangGraph 노드 모듈성 (Foundation, 강조 카드)
  · AXIS 02 현장·사업부 수평 확장 (Hi-tech → SK ecosystem)
  · AXIS 03 MPRS 영역 수직 확장 (P-Construction → R/P-Procure/M)
- 섹션 라벨: 'Roadmap' → 'Scalability · 확장성' (anchor id=roadmap 유지)
- Axis 03 정량 효과: 예상공기 검토시간 50% 절감
  (Hi-tech 정보화 과제 요청서 기준)

spec: docs/superpowers/specs/2026-05-20-cpia-landing-scalability-section-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Done Criteria

- [ ] `ScalabilitySection.tsx` 전체 교체 적용
- [ ] 5536 dev server 에서 새 화면 시각 확인
- [ ] `npm run build` 통과
- [ ] B_Track 에 커밋 완료
