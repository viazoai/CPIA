# CPIA E2E Audit Report (2026-05-17)

> Spec: `docs/superpowers/specs/2026-05-17-cpia-e2e-audit-design.md`
> Plan: `docs/superpowers/plans/2026-05-17-cpia-e2e-audit-plan.md`
> Branch: A_Track HEAD `1acf71e`
> 회귀 baseline (Task 0 Step 0.2): 183 passed in 569.85s — `pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -p no:slow --tb=no -q`. 직전 cycle (PR #15 머지 시점) 의 183 과 동일 — 본 audit 가 시작될 때 회귀 0 건. (참고: `-p no:slow` 는 slow plugin 부재로 무효, 실제로는 unit + slow + integration + E2E 전부 통과)
> PM 원안: `planning/CPIA_PoC_실행계획_v2.md`

---

## 0. Executive Summary

(Task 5 Step 5.3 에서 작성 — 일치도 분포 + 우선순위 #1~#3 + 회귀 + Azure 비용)

---

## 1. 단계별 매트릭스

### 1.1 Collector
(Task 2 Step 2.1)

### 1.2 Parser
(Task 2 Step 2.2)

### 1.3 Mapper
(Task 2 Step 2.3)

### 1.4 HIL 1 — drift 1호
(Task 2 Step 2.4)

### 1.5 Atomizer
(Task 2 Step 2.5)

### 1.6 Reporter — drift
(Task 2 Step 2.6)

### 1.7 Forecaster
(Task 2 Step 2.7)

### 1.8 HIL 2
(Task 2 Step 2.8)

### 1.9 Optimizer
(Task 2 Step 2.9)

### 1.10 Dashboard
(Task 2 Step 2.10)

---

## 2. 컨셉 v1→v2 cross-cutting

(Task 3 Step 3.2 — 6 변경 매트릭스)

### 2.7 Synthetic 변동/회복 패턴 매트릭스

(Task 3 Step 3.3 — drift 후보 #7 + #8)

---

## 3. 의도된 변경 (drift 제외, marked)

(Task 3 Step 3.4 — Azure / Next.js / PG+Chroma / Synthetic 90일 4 marked)

---

## 4. 시뮬 시나리오 4 건 결과

(Task 5 Step 5.1 — raw 부록 4 링크 + 검증 포인트 충족 여부)

---

## 5. 추가 발견 드리프트

(Task 4 Step 4.2 — 시뮬 raw + 매트릭스에서 새로 드러난 항목)

---

## 6. Limitation

(Task 5 Step 5.2 — LLM 비결정성 컬럼 + 시뮬 1 회 한계 + audit 범위 외)
