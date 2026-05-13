# CPIA v2 파이프라인 — Hi-tech사업 Activity 커버리지 분석

---

## 1. 분석 개요

| 항목 | 내용 |
|------|------|
| 분석 목적 | CPIA PoC v2 파이프라인이 Hi-tech사업 Activity 중 얼마나 커버 가능한지 정량 측정 및 예상 임팩트 산출 |
| 데이터 원본 | `TASK 및 Activity 취합 및 분석_원본자료_1차검토.xlsx` — 시트: `조정 Activity` |
| 필터 조건 | B열(조직명) = "Hi-tech사업" |
| 분석 기준일 | 2026-05-12 |
| 총 분석 건수 | **321건 / 7,708h (월투입시간 합계)** |

**CPIA v2 파이프라인 구성** (7개 Agent):

```
Collector → Parser → Mapper → Atomizer → Reporter → Forecaster → Optimizer
```

**커버리지 분류 기준:**

| 분류 | 정의 |
|------|------|
| **직접 커버** | v2 파이프라인 2개 이상 Agent가 해당 Activity를 자동화 처리 가능 |
| **부분 커버** | v2 파이프라인 1개 Agent만 대응 가능하거나 일부 단계만 자동화 가능 |
| **커버 불가** | CCTV/드론 Vision AI, CAD 직접 생성, IoT 제어 ML, 물리적 현장 운영 등 v2 범위 밖 |

---

## 2. 전체 Hi-tech Activity 현황 요약

### 2.1 전체 규모

| 지표 | 값 |
|------|-----|
| 총 Activity 건수 | 321건 |
| 총 월투입시간 | 7,708h |
| 연간 환산 공수 | 92,496h |
| FTE 환산 (176h/월 기준) | **43.8 FTE** |

### 2.2 팀별 Activity 분포

| 팀명 | 건수 | 월투입시간(h) | 비중 |
|------|------|--------------|------|
| Y-1 Ph-1 OBL | 38 | 1,602 | 20.8% |
| Y-1 Ph-1 IBL | 60 | 790 | 10.2% |
| Y-1 Ph-1 설계 | 31 | 1,111 | 14.4% |
| Indiana Fab HAC | 19 | 614 | 8.0% |
| P&T 3 증축 | 14 | 496 | 6.4% |
| Air솔루션팀 | 5 | 770 | 10.0% |
| Hi tech_청주 M15X PJT_IBL | 17 | 349 | 4.5% |
| Hi-tech예산관리팀 | 13 | 360 | 4.7% |
| M15X OBL & PT7 OBL | 19 | 357 | 4.6% |
| Indiana Fab Design | 8 | 202 | 2.6% |
| Water솔루션 | 17 | 180 | 2.3% |
| 용인산단사업추진팀 | 7 | 180 | 2.3% |
| 기획팀 | 5 | 175 | 2.3% |
| 사업관리2팀 | 20 | 190 | 2.5% |
| 기타 (6개 팀) | 48 | 332 | 4.3% |

> **핵심 5개 팀** (Y-1 Ph-1 OBL·IBL·설계, Indiana Fab HAC, P&T 3 증축)이 전체 시간의 **59.8%** 를 차지.

---

## 3. CPIA v2 파이프라인 커버리지

### 3.1 전체 커버리지 요약

| 분류 | Activity 수 | 월투입시간 (h) | 시간 비중 |
|------|------------|--------------|---------|
| **직접 커버** | **190건** | **4,317h** | **56.0%** |
| **부분 커버** | **100건** | **2,467h** | **32.0%** |
| **커버 불가** | **31건** | **924h** | **12.0%** |
| **합계** | **321건** | **7,708h** | 100% |

**커버 가능 범위 소계 (직접 + 부분):** 290건 / 6,784h **(88.0%)**

---

### 3.2 파이프라인 단계별 대응 Activity 현황

| Agent | 대응 건수 | 대응 월시간 (h) | 주요 담당 업무 유형 |
|-------|---------|--------------|-----------------|
| **Collector** | 250건 | 5,922h | 작업일보·보고서 파일 수집, 엑셀·PDF 감지, 메시지 수신 |
| **Parser** | 255건 | 5,664h | 비정형 텍스트 구조화, 조항 추출, OCR 처리 |
| **Mapper** | 100건 | 2,028h | WBS 코드 매핑, 법령 기준 비교, 단가 유사도 매칭 |
| **Atomizer** | 56건 | 2,101h | 과거 PJT 데이터 임베딩, LL 적재, 기준 문서 인덱싱 |
| **Reporter** | 146건 | 3,140h | Daily/Weekly Report 자동 생성, 발주처 보고서, 리스크 리포트 |
| **Forecaster** | 91건 | 2,148h | 생산성 진단, 공정 지연 예측, 단가 적정성 진단 |
| **Optimizer** | 38건 | 876h | 투입 인력 최적화, 리스크 대응 시나리오, 불합리 개선 조언 |

> Agent는 1개 Activity에 복수 대응 가능. 위 집계는 중복 포함.

---

### 3.3 직접 커버 Activity 목록 (상위 30개 — 시간 기준)

| 행번호 | 팀명 | 과업 | 활동 (요약) | 월시간(h) | 대응 Agent | 분류 근거 |
|--------|------|------|------------|---------|-----------|---------|
| 246 | Y-1 Ph-1 OBL | 작업일보 취합 및 작성 | BP별 작업일보 취합 및 Summary 작성 (매일) | 400 | Collector·Parser·Reporter | 파일 수집→파싱→통합 리포트 |
| 171_1~2 | Air솔루션팀 | 기술 지식 Pool 기반 의사결정 자동화 | 기술 자료 자동 분류/요약/관계도·이력 연결 | 330 | Atomizer·Forecaster·Reporter | 문서 임베딩→RAG Q&A |
| 247 | Y-1 Ph-1 OBL | Quantity Status Report 작성 | 공종별 주요 물량 Status Report (매일/주1회) | 200 | Collector·Parser·Mapper·Reporter | 데이터 취합→WBS 매핑→리포트 |
| 248 | Y-1 Ph-1 OBL | Progress Status Report 작성 | Phase/Discipline별 공정률 산출 (주1회) | 160 | Collector·Parser·Mapper·Reporter | 공정 데이터→WBS 매핑→리포트 |
| 142_1~3 | Hi-tech예산관리팀 | 신규단가 협의 | 품명·규격 검토, 단가 탐색·제안, 인터넷 실거래가 조사 | 120 | Collector·Parser·Mapper·Forecaster | 단가 파싱→유사도 매핑→적정 단가 진단 |
| 127 | 기획팀 | Global Risk Sensing | Hi-tech Risk 실시간 분석 | 100 | Collector·Parser·Atomizer·Forecaster·Optimizer | 리스크 데이터→임베딩→RAG→대응 조언 |
| 198 | P&T 3 증축 | 발주처 보고용 Weekly/Monthly Report 자동 작성 | Weekly/Monthly Report 보고 | 100 | Collector·Parser·Mapper·Reporter | 데이터 취합→WBS 매핑→리포트 자동 생성 |
| 202 | P&T 3 증축 | 콘크리트 타설 및 양생 품질 관리 | PJT 종료 시점 예측 (월 1회) | 100 | Collector·Atomizer·Forecaster·Optimizer | 공정 이력→RAG 예측→일정 최적화 |
| 204 | P&T 3 증축 | 도급 내역 기반 WBS Code 자동 매칭 | 도급 Product별 WBS Code 자동 산정 | 100 | Collector·Parser·Mapper | WBS 의미 기반 매핑 핵심 기능 |
| 289 | Indiana Fab HAC | CWP 분석 및 Forecast Schedule 작성 | Construction Work Package Schedule 분석 | 96 | Collector·Atomizer·Forecaster·Optimizer | 공정 데이터→임베딩→RAG 예측 |
| 141_1~2 | Hi-tech예산관리팀 | 작업일보를 활용한 생산성 분석 | 물량·인력 Data 정리, CPMS 기준 생산성 비교 | 90 | Collector·Parser·Atomizer·Forecaster·Optimizer | 생산성 데이터→Forecaster 진단 |
| 197_1~3 | P&T 3 증축 | 작업일보 | BP사 데이터 취합, 이상치 검증, Summary 작성 | 88 | Collector·Parser·Reporter | 파일 수집→파싱→통합 리포트 |
| 143_1~3 | Hi-tech예산관리팀 | 예산내역 검토 | 항목별 오류 검토, 임시품목 대체 검토, 요율 적정성 검토 | 80 | Collector·Parser·Mapper·Reporter | 내역서 수집→오류 파싱→기준 매핑 |
| 217_1~3 | Y-1 Ph-1 IBL | 공사비 추정 판단 지원 | 변경 항목 자동 분류, 증감 금액 산출, 검증 포인트 도출 | 80 | Collector·Parser·Mapper·Reporter | 내역서 비교→WBS 매핑→원가 리포트 |
| 262_1~3 | Y-1 Ph-1 설계 | LINE LIST 작성 | P&ID Line 자동 인식, Line Condition 자동 완성, List 자동 작성 | 80 | Collector·Parser·Mapper·Reporter | 설계 문서→구조화→리스트 생성 |
| 265 | Y-1 Ph-1 설계 | 법규 및 하이닉스 기준 분석 | 설비 설계 법규(설비법·화관법·고압가스법) 및 하이닉스 기준 검토 | 80 | Collector·Parser·Mapper·Reporter | 법령 문서→조항 파싱→기준 매핑 |
| 121 | Hi tech_청주 M15X PJT_IBL | 생산성을 고려한 최적의 공정률 관리 | 생산성·공정률 분석, 계획 수립 | 75 | Collector·Parser·Atomizer·Forecaster·Optimizer | 생산성 전 파이프라인 커버 |
| 291_1~3 | Indiana Fab HAC | 자재 과부족 예측 시스템 | BM 기반 소요 물량, 자재 입고 분석, 과부족 예측 | 70 | Collector·Parser·Forecaster·Optimizer | 자재 데이터→예측→최적화 조언 |
| 288_1~3 | Indiana Fab HAC | Progress Report 작성 | 설계·구매·시공 Input 취합, Progress 산정, Overall 작성 | 64 | Collector·Parser·Mapper·Reporter | Progress 데이터→WBS 매핑→리포트 |
| 144_1~3 | Hi-tech예산관리팀 | 단가정의서 Update | 단순 오류 검토·수정, 단가 불일치 Comment, 법적 기준 변경 개정 제안 | 60 | Collector·Parser·Mapper·Forecaster | 단가 데이터→유사도 매핑→진단 |
| 158 | Sys. Eng팀 | 설계 적합성 평가 | 자료 유형 무관 인식 및 신속한 검색 가능 | 60 | Atomizer·Forecaster | 멀티포맷 문서 임베딩→RAG 검색 |
| 219 | Y-1 Ph-1 IBL | PJT 현황 점검 | 정형화된 Daily Report 기반 Progress Status 및 Milestone Check | 60 | Collector·Parser·Reporter | Daily Report→Progress Status 자동 집계 |
| 257_1~3 | Y-1 Ph-1 설계 | 미팅 MOM 자동 작성 | 음성→텍스트 변환, 자료 참조, 자동 회의록 작성 | 50 | Parser·Reporter | STT→구조화 회의록 생성 |
| 286_1~3 | Indiana Fab HAC | 견적 단가 적정성 검토 | Norm 기반 예산 작성, 발주 단가 분석, CBE 작성 | 50 | Collector·Parser·Mapper·Forecaster | 단가 수집→파싱→적정성 진단 |
| 236_1~2 | Y-1 Ph-1 OBL | 품의 Format 작성 및 결재선 자동화 | 최적 품의 Format 자동 반영, 결재선 자동 지정 | 50 | Collector·Parser·Reporter | 문서 수집→파싱→표준 리포트 생성 |

---

### 3.4 부분 커버 Activity 주요 항목

| 과업 유형 | 대표 Activity | 월시간(h) | 대응 Agent | 제한 사유 |
|----------|-------------|---------|-----------|---------|
| 설계 기술 심의 | 설계-시공 기술심의 과거자료 완성도 확인 | 20 | Atomizer·Forecaster | 과거 문서 RAG 검색 가능, 최종 기술 판단은 H-i-L |
| 신기술 탐색 | 관련 특허 및 선행기술 유무 조사 | 110 | Collector·Parser·Atomizer | 외부 특허DB 직접 크롤링 별도 필요 |
| 외기 조건 분석 | 지역별 외기 환경 조건 분석 | 40 | Collector·Parser | 외부 기상 API 연동 추가 필요 |
| 시장 시황 분석 | 원자재 가격 변동 모니터링 | 10 | Collector·Parser·Reporter | 외부 스크래핑 확장 시 커버 가능 |
| 문서 등록·이력 | 도면 도각 이력 확인, 설계 문서 Log Sheet | 30 | Collector·Mapper | 문서 등록 자동화 가능, 도면 직접 처리 불가 |
| 퇴직공제 데이터 | 퇴직공제 신고 Data 점검 | 288 | Collector·Parser | 데이터 정리 가능, 법정 전산 신고는 별도 |
| 운전 데이터 KPI | CSRO 일·주간 KPI 산출·대시보드 | 50 | Collector·Parser·Reporter | KPI 계산 가능, 이상 탐지 ML 모델은 별도 |

---

### 3.5 커버 불가 Activity 목록

| 행번호 | 팀명 | 과업 | 불가 사유 | 대안 AI 과제 |
|--------|------|------|---------|------------|
| 227_1~3 | Y-1 Ph-1 IBL | 현장 안전 및 품질 관리 | 안전장비 착용 감지·위험구역 감지·드론 공정률 | **Vision AI 과제** |
| 292_1~3 | Indiana Fab HAC | CCTV/드론 기반 안전 System | PPE 미착용·추락·낙하물 자동인식 | **Vision AI 과제** |
| 293 | Indiana Fab HAC | 현장 사진 설치 완료 자동 측정 | 현장 사진 기반 Vision AI | **Vision AI 과제** |
| 276_1~2 | Y-1 Ph-1 설계 | 배관 평면도 작성 (PIPING PLAN DWG) | CAD 도면 직접 생성 | **CAD AI 자동화 과제** |
| 253 | Y-1 Ph-1 OBL | 일일 시공 현황 CAD화 | CAD 기반 시공 현황 도면화 | **CAD AI 자동화 과제** |
| 260 | Y-1 Ph-1 설계 | 전기 PNL 배치 적정성 검토 | 전문 설비 설계 기술 판단 | **설계 전문 AI 과제** |
| 261 | Y-1 Ph-1 설계 | Tray 및 Cable Route 검토 | 전문 설비 설계 기술 판단 | **설계 전문 AI 과제** |
| 271 | Y-1 Ph-1 설계 | 구조설계 의사결정 Agent | 구조물 형식 기술 판단 | **설계 전문 AI 과제** |
| 274 | Y-1 Ph-1 설계 | Concept 설계 기기 배치 검토 | 기기 배치 적정성 설계 판단 | **설계 전문 AI 과제** |
| 284 | Indiana Fab Design | Space Management 최적 Route | 3D Space 최적화 | **설계 전문 AI 과제** |
| 157 | Sys. Eng팀 | Pipe Rack 하중 예측 | 구조 설계 엔지니어링 | **설계 전문 AI 과제** |
| 168_1~2 | Water솔루션 | 운전 이상·리스크 자동 진단 | IoT 운전 패턴 ML 모델 | **설비 제어 AI 과제** |
| 169_1~2,4 | Water솔루션 | 세정(CIP/CEB) 예측·운전 전략 | IoT 운전 ML 모델 | **설비 제어 AI 과제** |
| 210_1 | Y-1 Ph-1 IBL | 법정 안전보건교육 운영·평가 | 법정 교육 시스템 운영 | **e-Learning 플랫폼** |
| 213_1~2 | Y-1 Ph-1 IBL | 안전보건 게시판 QR 코드 연동 | QR·영상 물리 운영 | **현장 운영 시스템** |
| 125_1~2 | 기획팀 | 인사발령 품의·명령 처리 | ERP 인사 트랜잭션 | **ERP 연동 RPA** |
| 154_1 | 팀 | 타각·위치정보 동선 분석 | 물리적 IoT 동선 모니터링 | **위치 추적 IoT 과제** |
| 230_1~2 | Y-1 Ph-1 IBL | AI 기반 인력 Control (동선 체크) | 물리적 IoT 동선 모니터링 | **위치 추적 IoT 과제** |
| 180_2 | M15X OBL & PT7 OBL | 전기실 운영 통일성 현장 적용 | 현장 물리 운영 | 해당 없음 |
| 146_3 | 팀 | 시공성 종합 검토 권고사항 도출 | 현장 전문 시공성 판단 | H-i-L 전문가 판단 |

---

## 4. 예상 Impact

### 4.1 절감 시간 계산

**자동화율 가정:**
- 직접 커버: 해당 Activity 공수의 **80% 절감**
- 부분 커버: 해당 Activity 공수의 **40% 절감**

| 구분 | 월투입시간(h) | 자동화율 | 월 절감 예상(h) |
|------|------------|--------|--------------|
| 직접 커버 (190건) | 4,317 | 80% | 3,454 |
| 부분 커버 (100건) | 2,467 | 40% | 987 |
| **합계** | **6,784** | — | **4,441** |

### 4.2 연간 절감 공수 및 FTE 환산

| 지표 | 값 |
|------|-----|
| 월 절감 예상 시간 | **4,441h/월** |
| 연간 절감 예상 시간 | **53,292h/년** |
| FTE 환산 (월 176h 기준) | **303 FTE** |
| 비용 절감 추정 (1.2억원/FTE·년) | **약 363억원/년** |

> **참고:** Hi-tech사업 전체 월투입시간(7,708h)의 절감률은 **57.6%** 에 해당.

### 4.3 팀별 예상 절감 시간

| 팀명 | 직접(h) | 부분(h) | 월 절감 예상(h) | 연 절감(h) | FTE |
|------|--------|--------|--------------|----------|-----|
| Y-1 Ph-1 OBL | 981 | 596 | 1,023 | 12,274 | 69.7 |
| Y-1 Ph-1 설계 | 405 | 286 | 438 | 5,261 | 29.9 |
| Air솔루션팀 | 330 | 440 | 440 | 5,280 | 30.0 |
| P&T 3 증축 | 496 | 0 | 397 | 4,762 | 27.1 |
| Y-1 Ph-1 IBL | 493 | 239 | 490 | 5,880 | 33.4 |
| Indiana Fab HAC | 414 | 0 | 331 | 3,974 | 22.6 |
| Hi-tech예산관리팀 | 350 | 10 | 284 | 3,408 | 19.4 |
| Hi tech_청주 M15X PJT_IBL | 269 | 80 | 247 | 2,966 | 16.9 |
| M15X OBL & PT7 OBL | 40 | 307 | 155 | 1,858 | 10.6 |
| 기타 | 539 | 509 | 635 | 7,619 | 43.3 |

---

## 5. 커버 불가 영역 분석 및 인접 AI 과제

### 5.1 카테고리별 불가 영역

| 카테고리 | Activity 수 | 월시간(h) | 연관 AI 과제 |
|---------|------------|---------|------------|
| Vision AI (CCTV·드론·현장 사진) | 7건 | 300h | 건설 현장 안전 Vision AI PoC |
| 설계 전문 AI (CAD·배치·구조) | 8건 | 490h | 설계 자동화 AI / BIM 연동 AI |
| IoT 제어 AI (운전 데이터 ML) | 5건 | 60h | 설비 운영 최적화 AI (Water솔루션) |
| ERP/시스템 연동 (인사·법정신고) | 3건 | 40h | RPA 또는 ERP API 연동 과제 |
| 물리적 현장 운영 | 5건 | 0~34h | 해당 없음 (시스템 범위 밖) |
| IoT 동선 모니터링 | 3건 | 0h | 현장 위치 추적 IoT 과제 |

### 5.2 커버 가능성 업그레이드 시나리오

| 현재 분류 | 조건 | 업그레이드 후 |
|---------|------|------------|
| 부분 커버 (신기술 탐색, 특허 조사) | 외부 특허DB API 연동 Collector 확장 | 직접 커버 전환 가능 |
| 부분 커버 (자재 시황 분석) | 외부 가격 정보 스크래핑 Collector 추가 | 직접 커버 전환 가능 |
| 부분 커버 (퇴직공제 신고 데이터 점검) | 공제회 시스템 API 연동 | 직접 커버 전환 가능 |
| 부분 커버 (운전 KPI 대시보드) | Water솔루션 전용 IoT Agent 추가 | 직접 커버 전환 가능 |

---

## 6. 결론 및 권고

### 6.1 핵심 발견

1. **Hi-tech사업 전체 321건 Activity 중 직접 커버 190건(59.2%), 부분 커버 100건(31.2%)으로** CPIA v2 파이프라인이 실질적으로 **88% 이상의 Activity에 기여 가능**하다.

2. **월투입시간 기준으로는 전체 7,708h 중 6,784h(88%)가 커버 범위**에 포함되며, 이 중 직접 커버가 4,317h(56%)로 파이프라인 핵심 효과를 발휘하는 영역이다.

3. **예상 임팩트는 월 4,441h 절감 / 연간 303 FTE / 약 363억원** 규모로 추정된다. 이는 Hi-tech사업부 현재 투입 공수의 절반 이상을 자동화한다는 의미이다.

4. **Collector와 Parser가 전체 커버 Activity의 80% 이상에 공통 적용**되며, 두 Agent가 v2 파이프라인의 핵심 게이트웨이 역할을 한다.

5. **커버 불가 31건(924h)은 Vision AI·설계 전문 AI·IoT 제어 AI 등 v2 범위 밖의 전문 AI 과제**로 분리하여 별도 PoC를 구성하는 것이 적합하다.

### 6.2 우선순위 권고

| 우선순위 | 추천 시작점 | 예상 월 절감 | 근거 |
|---------|----------|-----------|------|
| **P1** | Y-1 Ph-1 OBL — 작업일보 취합·Progress Report | 1,023h/월 | 가장 큰 시간 절감 단일 팀, Collector-Parser-Reporter 3-Agent 표준 플로우 |
| **P2** | Hi-tech예산관리팀·사업관리2팀 — 단가 검증·내역서 검토 | 400h/월 | Mapper 핵심 Use Case, 품셈 기반 Forecaster 검증 병행 |
| **P3** | Y-1 Ph-1 설계 — Line List·법규 검토·회의록 | 438h/월 | 설계 문서 자동화 + 법령 매핑 + Reporter 전체 파이프라인 검증 |
| **P4** | Indiana Fab HAC — CWP Forecast·자재 과부족 예측 | 331h/월 | Forecaster-Optimizer 2개 상위 Agent 실전 검증 |
| **P5** | Air솔루션팀 — 기술 지식 Pool Agent | 440h/월 | Atomizer 임베딩·RAG Q&A 핵심 검증 |

### 6.3 차기 PoC 범위 제안

- **CPIA v3 확장 방향:** Collector에 외부 API 연동(특허DB, 자재 시황, 기상 데이터) 추가 → 현재 부분 커버 100건 중 약 30건 직접 커버 전환 가능
- **별도 Vision AI PoC:** 현장 CCTV 기반 안전 감지(7건, 300h/월) — 독립 Computer Vision 파이프라인
- **설계 전문 AI PoC:** P&ID 파싱·배관 경로 검증 (8건, 490h/월) — BIM·CAD API 연동 전문 과제
- **IoT 제어 AI PoC:** Water솔루션 CSRO 운전 이상 탐지 (5건, 60h/월) — 시계열 ML 전용 파이프라인

---

*분석 기준: 조정 Activity 시트 Hi-tech사업 321건 전수 분류. 월투입시간이 0h로 기록된 Activity는 집계에 포함되나 임팩트 계산에서 0h 처리됨.*
