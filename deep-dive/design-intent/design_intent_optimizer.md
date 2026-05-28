# Design Intent — optimizer

- **Generated**: 2026-05-26 (view_builder 752 → 1882 LOC, +1130; site_summary.py 141 LOC 신규; 산식 A · MEDIAN · 4× perf · 4섹션 풍부화 cycle)
- **Git SHA (baseline → HEAD)**: `ef7c6cd` → `1ba783f` (A_Track, "Merge origin/main into A_Track — Mock 재설계 PR #40 머지 전 sync")
- **Pair file**: `../architecture_overview.md`, `../deep_dive_optimizer.md` (843줄, 본 카드의 raw grounding)
- **Working tree**: 1 줄 변경 잔존 — `view_builder.py:1447` `AND ma.trade IN ('건축', '토목')` 1 줄 삭제 (다른 세션 — v2 산출 설비/전기까지 확장 의도). 미커밋 → 이슈 #1.
- **Range (절대경로 + LOC, ~3,641 합계)**:
  - `pipeline/agents/optimizer/agent.py` — 227 LOC (이전 199 → +28)
  - `pipeline/agents/optimizer/prompt.py` — 316 LOC (이전 315, 변경 1줄)
  - `pipeline/agents/optimizer/retrieve.py` — 206 LOC (이전 161 → +45, INCIDENT 5→9종)
  - `pipeline/agents/optimizer/site_summary.py` — **141 LOC (신규 21c10f7)**
  - `pipeline/agents/optimizer/synthetic_v2.py` — 363 LOC (변경 없음)
  - `pipeline/agents/optimizer/synthetic_daily_report.py` — 498 LOC (변경 없음)
  - `pipeline/agents/optimizer/view_builder.py` — **1882 LOC (이전 752 → +1130, 신규 v2 산식 + 산식 A + cold_start + T17 fix)**
  - `__init__.py` 8 LOC
- **본 cycle 7 핵심 commit**: `c0a0641` (s_curve 산식 A) · `21c10f7` (site_summary) · `82bb8af` (4섹션 풍부화) · `690c305` (4× perf) · `e9b66d4` (MEDIAN fix) · `2c2ba75` (T17 quadrant matching) · `d79a438` (9 keyword retrieve).
- **스펙**:
  - `docs/superpowers/specs/2026-05-16-cpia-optimizer-hil2-design.md` (21 결정)
  - `docs/superpowers/specs/2026-05-17-cpia-hil1-forecaster-reporter-design.md` §5.3
  - `docs/superpowers/specs/2026-05-19-cpia-reports-gap-and-parser-design.md` §3-5 (view_builder + scenarios)
  - `docs/superpowers/specs/2026-05-21-views-v2-...` (v2 4단 산식 cycle)

> **본 cycle 의 사용자 핵심 결정 (`c0a0641`)**: `_build_s_curve` 의 공정률 산식 재설계 — **WV × MH 가중 + activity 단위 매칭 + progress cap (산식 A)**. 시연 핵심 지표(현장 진척률)의 의미가 단순 `SUM(today_qty)/SUM(plan_total_qty)` (단위 혼합 무의미) → 단위 무관 가중 진척률로 바뀜.

---

## T1 — Function Index

### agent.py (227 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `OptimizerConfig` (dataclass) | agent.py:50 | `(azure_endpoint, azure_api_key, azure_api_version, llm_model, postgres_url, chroma_host, chroma_port, chroma_ssl=False, azure_timeout=60.0, azure_max_retries=3)` | LLM + PG + Chroma config 묶음 | — |
| `_compute_recovery_distribution` | agent.py:64 | `(cases: list[dict]) -> dict[str, int]` | 결정 #20 — Counter([c["recovery"]["recovery_days"] for c in cases]) → {"d+1": N, ..., "not_recovered": N}. LLM 응답 override (코드 값이 정답) | ✅ |
| `_apply_augmentation_weight` | agent.py:77 | `(rows: list[dict]) -> list[tuple[dict, float]]` | augmented row 0.5 가중, 일반 1.0. backfill 산출물 활용 | — |
| `_compose_row` | agent.py:85 | `(r, cases, llm_output, run_id) -> dict` | LLM 출력 + cases merge → optimizer_advice row | ✅ |
| `_call_azure_llm` | agent.py:101 | `(llm_input, cfg, azure) -> dict` | Azure gpt-5.1 호출 (fail-fast, 결정 #10). response_format=json_object | ✅ |
| `_call_azure_llm_async` | agent.py:116 | `async (llm_input, cfg, azure) -> dict` | sync `_call_azure_llm` 을 `asyncio.to_thread` 로 감쌈 — 실 병렬 효과 (★ `690c305`) | ✅ |
| **`optimize`** | agent.py:121 | `async (forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id=None, mapped=None) -> list[dict]` | **LLM advice 4× gather** + PG insert + view_builder 9 jsonb 산출 + daily_reports UPSERT (★ `690c305` + `7fa3dd9`) | ✅ |

### prompt.py (316 LOC)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `SYSTEM_PROMPT` | prompt.py:21 | constant (35 line) | 한글+영어, "권장/권고" tone, **degradation_cases 빈 array 분기 명시 (cold_start LLM 호출)** | — |
| `FEW_SHOT_MESSAGES` | prompt.py:62~278 | constant (3 user/assistant pair) | 회복 패턴 sample: 장비대기 D+1, 자재미입고 D+2, 미회복 우세 | — |
| `build_llm_user_input` | prompt.py:287 | `(forecast_row, degradation_cases) -> dict` | forecast row + degradation_cases (recovery merge 포함) → LLM user JSON | ✅ |

### retrieve.py (206 LOC, ★ 변경 `d79a438` + `82bb8af`)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `INCIDENT_KEYWORDS` | retrieve.py:25 | constant 9 (이전 5 → **+4 신규**: 인력부족/재작업/병행작업/사양변경) | seed TAG_TO_CONDS 7 tag 모두 발현 보장 (★ `d79a438`) | — |
| `_DEGRADATION_INCIDENTS` / `_ALL_INCIDENTS` | retrieve.py:37/38 | alias = INCIDENT_KEYWORDS | backward compat (이전 3 + 5 → 9 통일) | — |
| `_group_day_productivity` | retrieve.py:45 | `(metas_of_day, baseline_unit) -> float` | 당일 그룹 생산성 = Σtoday_qty[unit] / assigned_workers | — |
| `_group_baseline` | retrieve.py:58 | `(metadatas, company, l6_main, baseline_unit, *, l7_5_activity=None) -> Optional[float]` | 정상 row productivity 평균. None → cold_start | ✅ |
| `fetch_degradation_cases` | retrieve.py:91 | `(metadatas, documents, company, l6_main, today, baseline_unit, baseline_value, n=5, *, l7_5_activity=None) -> list[dict]` | Step 1 — incident **OR** prod 저하 (★ `82bb8af` AND→OR). worker_source 화이트리스트 제거 | ✅ |
| `fetch_recovery_trajectory` | retrieve.py:154 | `(metadatas, company, l6_main, case_date, today, baseline_unit, baseline_value, window=7, *, l7_5_activity=None) -> dict` | Step 2 — case_date+1 ~ +7, recovery_days = first ✓ (or None) | ✅ |

### site_summary.py (141 LOC, ★★ 신규 `21c10f7`)

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `SYSTEM_PROMPT` | site_summary.py:25 | constant (19 line) | "경영진 분석가" persona, 1~2단락 (200~300자), "통계 용어 금지" + "한자 금지" + JSON 출력 | — |
| **`build_site_summary_payload`** | site_summary.py:46 | `(*, report_date, site_id, kpi, scenarios, wp_summary, optimizer_view, s_curve) -> dict` | LLM 입력 payload **결정론적** dict build: top 3 risk wp + recommendations[0] | ✅ |
| **`generate_site_summary`** | site_summary.py:117 | `(payload, *, azure=None, model=None) -> str` | Azure JSON mode 호출, fail-fast | ✅ |

### view_builder.py (1882 LOC, 45 함수 7 phase) — ★★ 본 cycle 최대 변경

#### Phase 1 — EVM 산출 (v1, `_build_productivity_views`)
| Function | File:Line | Signature (단축) | One-line role | T2? |
|---|---|---|---|---|
| `_sanitize_case_pp` | view_builder.py:14 | `(raw_pp, master_pp, seed_key) -> float` | ChromaDB perperson 비정상 스케일 → master ±10% deterministic stub | — |
| `_sanitize_workers` | view_builder.py:33 | `(raw_w, master_w, seed_key) -> int` | assigned_workers > 50 → master ±10% 또는 raw/8 fallback | — |
| **`_build_productivity_views`** | view_builder.py:48 | `async (pg, run_id, site_id, today, forecast, mapped) -> dict` | EVM 4 segment: today + by_contractor + by_l6 + by_wp | ✅ |
| `_evm_for_group` | view_builder.py:79 | `async (pg, site_id, today, group_key) -> dict` | site 전체 EVM — 분모=마스터플랜, 분자=mapper_activities 전체 | ✅ |
| `_compose_evm` | view_builder.py:125 | `(plan_row, actual_row) -> dict` | EV/PV/AC/SPI/CPI 산식 | ✅ |
| `_evm_by_group` | view_builder.py:161 | `async (pg, site_id, today, group_key) -> dict[str, dict]` | company / l6_main 별 EVM. **actual anchor** (매핑된 group 만 표시) | ✅ |
| `_evm_by_wa_l6_company` | view_builder.py:238 | `async (pg, site_id, today) -> dict[str, dict]` | (wa, l6, company) WP 단위 EVM — wa 가 mapper 전용 키이므로 mapper anchor | ✅ |

#### Phase 2 — KPI / 4분면 / WP 표
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| **`_build_kpi`** | view_builder.py:284 | `async (pg, site_id, today, productivity) -> dict` | 헤더 KPI — productivity_today / spi / cpi / target / delay_days / expected_completion. **★ MEDIAN (`e9b66d4`)** | ✅ |
| `_bar_status` | view_builder.py:322 | `(cpi: float) -> str` | normal(≥90) / caution(≥80) / risk | — |
| `_build_contractor_bars` | view_builder.py:331 | `(productivity) -> list[dict]` | by_contractor → BarItem[] CPI desc sorted, baseline=90 | ✅ |
| `_build_trade_bars` | view_builder.py:352 | `(productivity) -> list[dict]` | by_l6 → BarItem[] | ✅ |
| `_compute_impact_p90` | view_builder.py:369 | `(raw_impacts) -> float` | P90 percentile (len≥10) 또는 max fallback | — |
| `_normalize_impact` | view_builder.py:378 | `(raw, p90) -> float` | raw → 0~100 cap (★ shadowing 위험: `_normalize_impact_share` 와 이름 충돌) | — |
| `_quadrant_label` | view_builder.py:385 | `(productivity, impact) -> str` | risk / caution / watch / safe | ✅ |
| `_wp_id_of` | view_builder.py:398 | `(wa, l6_main, company) -> str` | kebab-case wp_id (cub-철근콘크리트공사-남웅건설) | — |
| `_build_wa_lookup` | view_builder.py:409 | `(items) -> dict[(l6_main,company), list[wa]]` | `_build_optimizer_view` fan-out 입력 | ✅ |

#### Phase 3 — Cold start 진단 (LLM advice 없는 WP, ★ `c67f341` + `82bb8af`)
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_pick_cause` | view_builder.py:423 | `(pct, impact, delay_days, trade) -> str` | 8 cause 분기 — productivity × impact × delay × trade | ✅ |
| `_pick_recommendations` | view_builder.py:442 | `(pct, impact, delay_days, workers, trade) -> list[str]` | 5 rule 조합형 — 인력 +1 / 후속 영향 / 인터페이스 / 장비·자재 / 정상페이스 | ✅ |
| `_compose_diagnosis` | view_builder.py:460 | `(pp_master, pp_today, pct, unit, cause) -> str` | "이 작업은 보통 인당 X.XX 단위..." (≤140자) | — |
| `_compose_diagnosis_no_master` | view_builder.py:472 | `(pp_today, unit) -> str` | master 없음 단순 진단 | — |
| **`_build_deterministic_cold_start`** | view_builder.py:480 | `(q, master, chroma_cases, *, workers, risk_level, delay_days) -> dict` | advice 없는 WP 마다 deterministic 4 슬롯 (LLM 호출 0). `_sanitize_case_pp/_sanitize_workers` 통해 chroma noise 정정 | ✅ |

#### Phase 4 — ChromaDB lookup + Quadrant + WP summary
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_get_chroma_collection` | view_builder.py:597 | `() -> Collection` | `_chroma_singleton` 모듈 캐시 (530일 socket 누적 timeout 회피) | — |
| `_get_all_backfill_metas` | view_builder.py:611 | `() -> list[dict]` | `_chroma_metas_cache` 모듈 캐시 — backfill_v2 전체 metadata 1회 fetch | — |
| **`_fetch_chroma_cases_lookup`** | view_builder.py:627 | `async (items, today) -> dict[wp_id, list[dict]]` | 3단 fallback: (company, l6, l7_5) → (company, l6) → (l6, l7_5) → []. 메모리 bucket lookup | ✅ |
| `_fetch_chroma_cases_lookup_legacy` | view_builder.py:670 | `async (items, today) -> dict` | 개별 wp 별 col.get — backfill 시 timeout. deprecated | — |
| **`_build_quadrant`** | view_builder.py:719 | `async (pg, site_id, today, productivity) -> list[dict]` | 4분면 산점도 — raw_impact = SUM(plan_total_qty) × AVG(plan_mh), P90 normalize | ✅ |
| **`_build_wp_summary`** | view_builder.py:762 | `async (pg, site_id, today, productivity, quadrant_jsonb) -> list[dict]` | WP 표 — quadrant + baseline + status (v1 placeholder 4 필드는 v2 가 채움) | ✅ |

#### Phase 5 — S-curve (산식 A, ★★ 본 cycle 핵심 변경 `c0a0641`)
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_merge_curves` | view_builder.py:792 | `(planned, actual, recovery=None) -> list[dict]` | date 단위 datapoint 합성 (actual delta → cumulative 변환) | ✅ |
| `_extend_forecast` | view_builder.py:824 | `(merged, days_ahead=30) -> list[dict]` | 직전 7일 평균 rate × remaining_days. rate≤0 fallback = planned 일평균 × 0.7. dedup | ✅ |
| **`_build_s_curve`** | view_builder.py:880 | `async (pg, site_id, today) -> list[dict]` | **★★ 산식 A** — WV × MH 가중 + activity 단위 매칭 + progress cap | ✅ |

#### Phase 6 — Optimizer view + Scenarios
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| **`_build_optimizer_view`** | view_builder.py:1024 | `(advice_rows, forecast, mapped, wa_lookup=None) -> dict` | 4 섹션 진단 by_wp — `wa_lookup` fan-out (한 advice → 여러 wp_id 복사) | ✅ |
| `_coerce_date` | view_builder.py:1137 | `(v) -> date \| None` | asyncpg date vs jsonb str 둘 다 허용 | — |
| `_expand_recovery_to_days` | view_builder.py:1154 | `(dist: dict) -> list[int]` | recovery_distribution → 분위수 산출 가능 list (not_recovered +30 cap) | ✅ |
| `_percentile` | view_builder.py:1172 | `(days, q) -> int` | q ∈ [0,1]. len<4 idx, 그 외 `statistics.quantiles(n=100, method="inclusive")` | — |
| `_match_forecast_by_company_l6` | view_builder.py:1184 | `(advice, forecast) -> dict \| None` | (company, l6_main) lookup | — |
| `_scenario` | view_builder.py:1197 | `(no_action_date, recovery_days, case_count) -> dict` | 단일 시나리오 dict (recovery 0 → no_action pass) | — |
| **`_build_scenarios`** | view_builder.py:1215 | `(advice_rows, forecast) -> dict` | **★ 4 시나리오 (`3781e5b`)** — site + by_wp (no_action / optimistic_p25 / base_p50 / pessimistic_p75). 라벨↔분위수 swap 의도 (P75=낙관) | ✅ |

#### Phase 7 — v2 통합 산식 (★ NEW `_build_productivity_views_v2`, `38127ff` + 후속)
| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_compute_daily_quota` | view_builder.py:1275 | `(plan_total_qty, total_days) -> float` | 일일 quota = qty / days | — |
| `_simulate_today_qty` | view_builder.py:1282 | `(daily_qty, daily_workers, seed) -> dict` | productivity 분포 = 중심 85% + ±20% + 5%/5% outlier (60%/150%) | — |
| `_compute_productivity` | view_builder.py:1308 | `(perperson, master_perperson) -> float` | (인당 / 마스터 인당) × 100 | — |
| `_weighted_median` | view_builder.py:1315 | `(values, weights) -> float` | 가중 누적 50% 지점 | — |
| `_normalize_impact_share` | view_builder.py:1331 | `(impacts) -> list[float]` | share-of-total (일별 합 = 100%) — ★ `_normalize_impact` 와 이름 충돌 주의 | — |
| `_make_display_label` | view_builder.py:1348 | `(productivity_pct, perperson, unit) -> str` | "98.9% (3.20 ton/인)" 라벨 | — |
| `_status_of` | view_builder.py:1362 | `(pct) -> str` | normal(≥90) / caution(≥70) / risk | — |
| `_quadrant_of` | view_builder.py:1371 | `(prod, impact) -> str` | risk / caution / watch / safe (v2 thresholds) | — |
| `_group_perperson_unit` | view_builder.py:1381 | `(items) -> (avg, unit)` | wv-mean perperson + 단위 일관성 검증 (섞이면 None,None) | — |
| **`_build_productivity_views_v2`** | view_builder.py:1410 | `async (pg, site_id, today) -> dict` | **★ 신규 4단 산식** — 9 jsonb 통합 산출 + cold_start fan-out + scenarios + s_curve | ✅ |
| `_augment_history_if_sparse` | view_builder.py:1854 | `(items, min_count=5) -> list[dict]` | (company, l6) row < 5 → 동일 l6 다른 company 보충 (augmented=True) | ✅ |

### synthetic_v2.py (363 LOC) — 변경 없음

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `_BP_TOTAL` | synthetic_v2.py:28 | constant dict | 9/25 작업일보 BP사 총 인원 ({"남웅건설": 88, "세보엠이씨": 1387, "창원기전": 372}) | — |
| `generate_synthetic_v2_group` | synthetic_v2.py:35 | `(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days=90, seed=42, reference_date=None) -> list[dict]` | state machine 90일 시계열 (회복 룰 7건) | ✅ |

### synthetic_daily_report.py (498 LOC) — 변경 없음

| Function | File:Line | Signature | One-line role | T2? |
|---|---|---|---|---|
| `generate_fake_daily_report` | synthetic_daily_report.py:50 | `(report_date, scenarios, activity_pools, baseline_workers, baseline_qty, seed) -> list[Activity]` | Activity list 직접 생성 (Parser/Mapper skip) | ✅ |
| `_parse_scenario` | synthetic_daily_report.py:118 | `(scenario_str) -> dict` | `"company\|l6_main\|n\|incident\|prod_ratio\|workers_ratio\|unit"` 파싱 | — |
| `_check_synthetic_v2_loaded` | synthetic_daily_report.py:140 | `async (cfg) -> bool` | `worker_source=synthetic_v2` row 0 이면 abort | — |
| `_initial_state` | synthetic_daily_report.py:242 | `(run_id, report_date, mapped) -> dict` | `build_demo_graph` 진입 state | — |
| `build_demo_graph_config` | synthetic_daily_report.py | `() -> GraphConfig` | demo graph 용 config | — |
| `_main_cli` | synthetic_daily_report.py:355 | `async () -> None` | 9 step demo CLI (interactive resume 포함) | — |

---

## T2 — Issue Cards

### ★★ `_build_s_curve` — 공정률 산식 A 재설계 (본 cycle 핵심)

- **위치**: `pipeline/agents/optimizer/view_builder.py:880~1021`
- **시그니처**: `async def _build_s_curve(pg: PGClient, site_id: str, today: date) -> list[dict[str, Any]]`
- **이슈**:
  - git log: `c0a0641 ★★ feat(view-builder): 공정률 산식 재설계 — WV × MH 가중 + activity 매칭`
  - 이전 단순 `SUM(today_qty) / SUM(plan_total_qty)` 는 단위 일관성 부재 (m³+ton+개 혼합 합산 → 무의미)
  - 시연 핵심 지표(현장 진척률)의 의미가 바뀜
- **설계 의도**:
  - **단위 무관 가중 진척률**. WV (work value) × MH 가중으로 단위 다른 activity 들을 한 곡선으로 합성
  - planned 곡선과 actual 곡선이 **같은 분모** (site_total_weight) 로 환산되어 같은 좌표계에서 비교 가능
  - actual 의 **단조 누적 보장** — full_grid cross join 으로 "그날 작업 안 한 (wa, l6) 도 직전 cum 유지" → V자 dip 방지
  - **progress cap (LEAST 1.0)** — 마스터 초과 작업 시 100% clamp (overrun 누적 차단)
- **대응 패턴**:
  - 분모 (view_builder.py:897~905): `SELECT SUM(plan_wv * plan_mh_rev2)::float FROM activity_master WHERE site_id = $1 AND plan_wv IS NOT NULL AND plan_mh_rev2 IS NOT NULL`
  - planned[t] (view_builder.py:914~936): activity 단위 linear progress × `plan_wv × plan_mh_rev2`, generate_series(MIN(plan_start), gs_end, '1 day') CROSS JOIN LATERAL
  - actual[t] (view_builder.py:942~981): (wa, l6_main) 매칭, full_grid cross join 으로 cum 보장, `SUM(weight * LEAST(1.0, cum_qty / NULLIF(plan_qty, 0)))`
  - 환산 (view_builder.py:1017~1020): `round(min(100.0, p[k] / site_total_weight * 100), 2)`
- **관련**:
  - 호출자: `agent.py:212` (`s_curve_jsonb`), v2 `view_builder.py:1829`
  - BFF 소비: `web/lib/transforms.ts` deriveSCurve
- **Suspected related**:
  - `_extend_forecast` (view_builder.py:824) — 7일 평균 rate fallback 으로 outlier (mock 9-25 today_qty=6608) 흔들림 방지
  - `_merge_curves` (view_builder.py:792) — recovery 만 합성 (planned/actual 은 이미 가중 sum)

---

### ★★ `build_site_summary_payload` + `generate_site_summary` — site narrative 신규 (`21c10f7`)

- **위치**: `pipeline/agents/optimizer/site_summary.py:46` + `site_summary.py:117` (141 LOC 신규 파일)
- **시그니처**:
  - `build_site_summary_payload(*, report_date, site_id, kpi, scenarios, wp_summary, optimizer_view, s_curve) -> dict`
  - `generate_site_summary(payload, *, azure=None, model=None) -> str`
- **이슈**:
  - git log: `21c10f7 ★★ feat(site-summary): Optimizer LLM 산출 site 수준 narrative + FE 룰베이스 교체`
  - FE 의 룰베이스 narrative 가 시연용으로 부족 → 경영진 1~2단락 자연어 보고
  - LLM 출력 변동성 — payload 를 **결정론적** dict 로 build 하여 입력 변동 차단
- **설계 의도**:
  - 입력 payload (`build_site_summary_payload`) 가 **결정론적**: s_curve 의 report_date 시점 planned/actual, top 3 risk wp (impact desc), 각 wp 의 LLM diagnosis + recommendations[0]
  - LLM (`generate_site_summary`) 는 Azure JSON mode, fail-fast — 호출자가 try/except
  - "통계 용어 (P25/P50/P75, MH 가중, EVM 등) 사용 금지", "한자 사용 금지", "추측/과장 금지", 200~300자
  - cold_start diagnosis 는 None 처리 (site_summary.py:81~82) — placeholder 가 narrative 에 새지 않음
- **대응 패턴**:
  - payload (site_summary.py:101~114): `{report_date, site_id, progress_pct: {planned, actual}, gap_pct, delay_days, ai_recovery_days (base_p50), expected_completion: {if_no_action, ai_scenario, plan}, top_risk_wps: [{wp_name, trade, diagnosis, top_recommendation}, ...]}`
  - top 3 산출 (site_summary.py:71~99): `wp_summary` 에서 impact > 0 filter → impact desc top 3 → optimizer_view.by_wp[wp_id].diagnosis + recommendations[0]
  - LLM 호출 (site_summary.py:135~140): `messages = [system, user(json.dumps(payload))]`, `response_format={"type":"json_object"}` → `parsed["summary"]` 반환
- **관련**:
  - 호출자: **production 그래프 미연결** — `scripts/backfill_daily_report_views_v2.py:141~172` `--with-summary` flag 만 호출 (이슈 #3)
  - 영속: `daily_reports.site_summary_text` (UPDATE)
- **Suspected related**:
  - `_build_kpi` / `_build_scenarios` / `_build_wp_summary` / `_build_optimizer_view` / `_build_s_curve` — 모두 입력 dependency

---

### ★ `optimize` — Orchestration Core (4× perf + 9 jsonb)

- **위치**: `pipeline/agents/optimizer/agent.py:121` (~107 LOC)
- **시그니처**: `async def optimize(forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id=Optional[str], mapped=Optional[list]) -> list[dict]`
- **이슈**:
  - git log: `690c305 ★ perf(optimizer): optimize() forecast 루프 asyncio.gather + to_thread (4×)`
  - git log: `82bb8af feat(report): 4섹션 풍부화 — cold_start LLM 호출` — 이전 `_compose_cold_start_row` placeholder 폐기, `ba505da` dead code 제거
  - git log: `7fa3dd9 feat(optimizer): build view jsonb + daily_reports UPSERT (partial write 가드)`
  - 결정 #8 (retrieve 책임은 hil_2_node) + #10 (fail-fast) + #20 (recovery_distribution Counter)
- **설계 의도**:
  - **4× 단축 (`690c305`)**: 이전 순차 sync 루프 → `_call_azure_llm_async` (asyncio.to_thread) + `asyncio.gather(*tasks)`. semaphore 는 LLM 호출 부분만 감싸고 PG write 는 밖 (agent.py:160~163)
  - **cold_start LLM 호출 (`82bb8af`)**: cases < 3 도 LLM 호출 — `SYSTEM_PROMPT` 의 "degradation_cases 빈 array 분기" 활용. 사용자 검증 9/22 광건 fab cold_start placeholder 화면 push back 결과
  - **9 jsonb partial write 가드**: 각 컬럼별 try/except → `upsert_daily_report_view_col` (db.py:1062). 한 컬럼 실패해도 나머지 영속
  - **wa_lookup fan-out** (agent.py:191~204): `SELECT array_agg(DISTINCT wa) FILTER (WHERE wa IS NOT NULL) FROM mapper_activities GROUP BY l6_main, company` — 한 advice → 여러 wp_id 복사 (quadrant dot 의 wp_id 와 by_wp key 매칭 보장, spec §8.3)
- **대응 패턴**:
  - 입력: forecast, hil_2_selection, pre_optimizer_cases, run_id, today, cfg, site_id, mapped
  - 처리:
    - Azure client init (agent.py:149) + `sem = get_llm_semaphore()` (agent.py:157)
    - `_process_one(r, cases)` closure (agent.py:159): sem 안에서만 LLM 호출, PG write 는 sem 밖
    - forecast 루프 (agent.py:166~174) → tasks 등록 (key = `f"{r['company']}|{r['l6_main']}"`)
    - `advice_rows = list(await asyncio.gather(*tasks))` (agent.py:176)
    - PG connect → `insert_optimizer_advice` × N (agent.py:181~182)
    - view_builder 9 jsonb (agent.py:185~217): productivity_jsonb, kpi_jsonb, contractor_bars_jsonb, trade_bars_jsonb, quadrant_jsonb, wp_summary_jsonb, s_curve_jsonb, optimizer_view_jsonb, scenarios_jsonb
    - 9 컬럼 partial UPSERT (agent.py:218~222)
  - 출력: advice rows list
- **관련**:
  - 호출자: `pipeline/graph.py` optimizer_node (production) + `synthetic_daily_report.py` CLI
  - 영속: `optimizer_advice` (N row) + `daily_reports` (9 jsonb column)
- **Suspected related**:
  - **v2 변형**: `_build_productivity_views_v2` (view_builder.py:1410) — agent.py 는 v1 호출, backfill 은 v2 → 이슈 #5
  - `pipeline.agents._concurrency.get_llm_semaphore` — Azure rate limit 가드

---

### ★ `_build_kpi` — site KPI MEDIAN fix (`e9b66d4`)

- **위치**: `pipeline/agents/optimizer/view_builder.py:284~319` (+ v2 동일 SQL `view_builder.py:1693~1706`)
- **시그니처**: `async def _build_kpi(pg, site_id, today, productivity) -> dict`
- **이슈**:
  - git log: `e9b66d4 ★ fix(view_builder): site KPI delay_days AVG -> MEDIAN (outlier robust)`
  - AVG 산식 outlier: 동신패널 외장판넬 atomic 1행 dummy anomaly = 167,871일 → AVG=2,398 → KPI "지연 2,398일" 화면 표시 (사용자 push back)
  - MEDIAN: 정상 군집 (≈ 11일) 수렴 — outlier 1건은 max 로만 영향
- **설계 의도**:
  - **PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_days)** — 연속값 (delay_days 는 float)
  - **PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY expected_completion)** — 이산값 (date 는 정수 아님)
  - "일반적 그룹 delay" 의미. site KPI 가 outlier 1건에 끌려가지 않게.
- **대응 패턴**:
  - 입력: pg, site_id, today, productivity (이전 단계 산출)
  - 처리: site_evm 의 cpi/spi + forecasts MEDIAN delay
  - 출력: `{productivity_today, spi, cpi, target_productivity, delay_days, expected_completion}`
- **관련**:
  - 호출자: `agent.py:207` (`kpi_jsonb`), v2 동일 SQL block 도 `_build_productivity_views_v2`:1693
  - 의존: forecasts table (forecaster 산출)
- **Suspected related**:
  - 같은 SQL 패턴이 v1 (view_builder.py:295~309) 과 v2 (view_builder.py:1693~1706) 두 곳에 중복 — 둘 다 수정 필요

---

### ★ `_build_scenarios` — percentile 4 시나리오 (`3781e5b`)

- **위치**: `pipeline/agents/optimizer/view_builder.py:1215~1265`
- **시그니처**: `def _build_scenarios(advice_rows: list[dict], forecast: list[dict]) -> dict`
- **이슈**:
  - git log: `3781e5b optimizer: add _build_scenarios + scenarios_jsonb upsert` (2026-05-19)
  - migration: `infra/postgres/migrations/2026-05-19_scenarios_jsonb.sql`
  - spec: `2026-05-19-cpia-reports-gap-and-parser-design.md` §5.1~5.4
- **설계 의도**:
  - **4 시나리오** (no_action / optimistic_p25 / base_p50 / pessimistic_p75) — PM 이 시나리오별 expected_completion 비교 의사결정
  - **라벨 ↔ 분위수 swap (★ view_builder.py:1237~1241)**: `optimistic_p25` ← `_percentile(site_days, 0.75)` (P75 = 큰 recovery_days = 회복 길게 = 낙관), `pessimistic_p75` ← `_percentile(site_days, 0.25)` (P25 = 작은 recovery_days = 회복 짧게 = 비관). "최적화 공기" 표시값이 실제 최대 만회를 반영.
  - `not_recovered` → +30 일 cap (`_expand_recovery_to_days` view_builder.py:1154)
- **대응 패턴**:
  - 입력: advice_rows (recovery_distribution dict 포함), forecast (expected_completion)
  - 처리:
    - site_days = 모든 advice 의 `_expand_recovery_to_days` 병합
    - site_no_action = `max([_coerce_date(f.get("expected_completion")) for f in forecast])`
    - site_scenarios 4 keys 생성 (no_action / p25 / p50 / p75)
    - by_wp loop: `wp_id = _wp_id_of(f.get("wa"), advice.get("l6_main"), advice.get("company"))`, no_action_date = forecast row 의 expected_completion
  - 출력: `{site: {...}, by_wp: {wp_id: {...}}}`
- **관련**:
  - 호출자: `agent.py:216` (`scenarios_jsonb`), v2 `view_builder.py:1828`
  - 영속: `daily_reports.scenarios_jsonb`
  - BFF 소비: `web/lib/transforms.ts` deriveSCurve / recovery sub
- **Suspected related**:
  - `_compute_recovery_distribution` (agent.py:64) — input 원천
  - `_coerce_date` (view_builder.py:1137) — expected_completion date/str 안전 coerce
  - `site_summary.build_site_summary_payload` — base_p50 직접 소비 (site_summary.py:69)

---

### ★ `_build_productivity_views_v2` — Phase 1 통합 산식 (NEW, v1 과 산식 다름)

- **위치**: `pipeline/agents/optimizer/view_builder.py:1410~1846` (437 LOC, 사실상 9 jsonb 통합 산출)
- **시그니처**: `async def _build_productivity_views_v2(pg: PGClient, site_id: str, today: date) -> dict`
- **이슈**:
  - git log: `38127ff feat: _build_productivity_views_v2 통합 산식 (Task 9)` + 후속 phase2 C1~C9 (a8081b2 / 3271378 / 2d98a08 / c67f341 / 3029653 / 5d69a2f / 450c9a7 / f74cdd3)
  - **v1 ↔ v2 산식 다름**: v1 은 EVM (cum_actual_qty / plan_qty_full × plan_mh), v2 는 인당 비교 (perperson / master_perperson × 100, 150 clamp)
  - **v1/v2 병행 사용 위험 (이슈 #5)**: `agent.py:187` 은 v1 호출 (production graph), `scripts/backfill_daily_report_views_v2.py:125` 는 v2 호출 (backfill). 같은 컬럼 `productivity_jsonb` 다른 값
  - working tree 잔존 1 줄 (view_builder.py:1447) `AND ma.trade IN ('건축', '토목')` 제거 (이슈 #1) — v2 산출 대상 확장
- **설계 의도**:
  - **인당 단위 산식** — `perperson = today_qty / workers`, `master_perperson = plan_qty/total_days / (plan_mh/total_days/8)`, `productivity = perperson / master_perperson × 100 (clamp 150)`
  - **결정성 seed**: `hashlib.sha256(f"{today.toordinal()}|{l7_5_activity}|{company}").digest()[:4]` (view_builder.py:1468~1471) — `random.Random(seed)` 결과가 매일/매 그룹마다 결정론적, backfill idempotent
  - **9 jsonb 한 함수에서 통합** — kpi + productivity + contractor_bars + trade_bars + quadrant + wp_summary + optimizer_view + scenarios + s_curve 모두 산출 후 return
  - **cold_start fan-out 통합 (`5d69a2f` C7)**: `optimizer_view` 산출 후 quadrant 의 advice 없는 wp_id 를 `_build_deterministic_cold_start` 로 채움
  - **T17 quadrant ↔ by_wp 매칭 (`2c2ba75`, view_builder.py:1807~1810)**: `quadrant_ids = {q["wp_id"] for q in quadrant}`, `optimizer_view["by_wp"] = {k: v for k, v in ... if k in quadrant_ids}` → Jaccard 11% → 100%
- **대응 패턴**:
  - SQL (view_builder.py:1426~1450): `mapper_activities` LEFT JOIN LATERAL `(activity_master MIN(plan_start)/MAX(plan_finish)/SUM(qty)/SUM(mh) GROUP BY (site, company, l6, l7_5))`. `report_date BETWEEN m.ps AND m.pf` + `l7_5_activity IS NOT NULL`
  - row 별 산식 (view_builder.py:1454~1499): `_compute_daily_quota` → `_simulate_today_qty(seed)` → perperson → productivity → impact_raw
  - 집계: by_company (defaultdict) → company_prod, by_l6 → l6_prod, site_wv_median = `_weighted_median(company medians, sum_wv)`
  - wp_id 그룹 (view_builder.py:1596~1631): 같은 (wa, l6_main, company) 여러 mapper row → 통합. `agg_prod = _stats.median(prods)`, `agg_impact = sum(impacts)` (share-of-total)
  - optimizer_view + cold_start fan-out (view_builder.py:1782~1826)
  - return 9 jsonb dict (view_builder.py:1836~1846)
- **관련**:
  - 호출자: `scripts/backfill_daily_report_views_v2.py:125` (backfill 만, **production 미연결**)
  - 영속: `daily_reports` 9 jsonb 컬럼 (UPSERT 별도)
- **Suspected related**:
  - `_simulate_today_qty` / `_compute_productivity` / `_normalize_impact_share` / `_weighted_median` — 모두 v2 전용 helper
  - `_build_optimizer_view` (재사용) + `_build_deterministic_cold_start` (fan-out) + `_fetch_chroma_cases_lookup` + `_build_scenarios` + `_build_s_curve` — v2 가 모두 한 함수에서 chain

---

### ★ T17 quadrant ↔ by_wp wp_id 매칭 보강 (`2c2ba75`)

- **위치**: `pipeline/agents/optimizer/view_builder.py:1799~1826` (v2 안 sub-step)
- **시그니처**: (no signature — `_build_productivity_views_v2` inline block)
- **이슈**:
  - git log: `2c2ba75 ★ fix: T17 quadrant ↔ by_wp wp_id 매칭 보강`
  - `_build_optimizer_view` 가 advice_rows (설비 포함) 기반으로 by_wp 를 채우는데, quadrant (건축/토목 trade IN 필터) 와 wp_id 집합 달라 Jaccard 11%
  - Optimizer view 패널이 quadrant 점 클릭 시 빈 화면 (advice 없는 wp_id) → 사용자 push back
- **설계 의도**:
  - 2단계 fix:
    1. `optimizer_view["by_wp"] = {k: v for k, v in optimizer_view["by_wp"].items() if k in quadrant_ids}` (view_builder.py:1808~1810) — quadrant 에 없는 설비 advice 제거
    2. quadrant 의 나머지 wp_id 를 cold_start 로 채워 by_wp = quadrant 1:1 대응 (view_builder.py:1812~1824)
  - 결과: intersection = union = |quadrant| → Jaccard 100%
- **대응 패턴**:
  - 입력: quadrant (list[dict]), optimizer_view (dict)
  - 처리: quadrant_ids set 산출 → restrict + chroma_cases_lookup + cold_start fan-out
  - 출력: optimizer_view.by_wp ⊇ quadrant.wp_id 보장
- **관련**:
  - 의존: `_fetch_chroma_cases_lookup` (3단 fallback), `_build_deterministic_cold_start`, `forecast_by_wp` lookup
- **Suspected related**:
  - working tree 잔존 1 줄 (view_builder.py:1447, 이슈 #1) — `AND ma.trade IN ('건축', '토목')` 제거 시 quadrant 대상 확장 → T17 fix 의 1:1 매칭 보장 그대로 유효 (cold_start fan-out 이 더 많은 wp 채움)

---

### ★ retrieve.py — INCIDENT 9 종 확장 + degradation OR 완화 (`d79a438` + `82bb8af`)

- **위치**: `pipeline/agents/optimizer/retrieve.py:25~42` (상수), `retrieve.py:91~151` (`fetch_degradation_cases`)
- **시그니처**: `def fetch_degradation_cases(metadatas, documents, company, l6_main, today, baseline_unit, baseline_value, n=5, *, l7_5_activity=None) -> list[dict]`
- **이슈**:
  - git log: `d79a438 ★ feat(retrieve): incident keyword 9종 보강` — 5 → 9 (장비대기/자재미입고/돌관/우천/야간연장 + **인력부족/재작업/병행작업/사양변경**)
  - git log: `82bb8af feat(report): 4섹션 풍부화 — retrieve 완화` — AND → OR
  - 이전 AND 조건: `conditions ∋ incident AND prod < baseline×0.85` → backfill_v2 의 `conditions='[]'` 빈 string row 가 모두 차단됨 → 75사가 case=0 cold_start
  - worker_source 화이트리스트 (`synthetic_v2`, `mh_prorated`) → backfill_v2/dummy_seed 차단
- **설계 의도**:
  - **degradation 정의 완화** (retrieve.py:136~140): `has_incident = any(c in raw for c in _DEGRADATION_INCIDENTS)`, `is_degraded = prod < baseline_value * _DEGRADATION_RATIO`, `if not (has_incident or is_degraded): continue` — 둘 중 하나만 만족해도 case
  - **worker_source 화이트리스트 제거** (retrieve.py:125~127): 모든 source 인정 (synthetic_v2 + mh_prorated + backfill_v2 + dummy_seed)
  - **9 keyword**: seed TAG_TO_CONDS 의 7 tag 모두 발현 보장
  - `INCIDENT_KEYWORDS = _DEGRADATION_INCIDENTS = _ALL_INCIDENTS` 한 상수로 통일 (이전 3종 + 5종 split)
- **대응 패턴**:
  - 입력: Chroma metadatas + documents (hil_2 coll.get F5 1회 호출 결과), company, l6_main, today, baseline_*, n=5, *l7_5_activity*
  - 처리: filter (company is None → 동종 cross-company) → date desc bucket → has_incident OR is_degraded → top-N
  - 출력: list[dict] (date, conditions, productivity, assigned_workers, activities)
- **관련**:
  - 호출자: graph.py `hil_2_node` (graph.py:351~355)
  - 페어: `fetch_recovery_trajectory` (retrieve.py:154)
- **Suspected related**:
  - `_group_baseline` (retrieve.py:58) — baseline_value 산출 source
  - downstream: `_compute_recovery_distribution` (agent.py:64) — 본 함수 cases 의 recovery_days 소비

---

### ★ optimizer 4 섹션 풍부화 + cold_start LLM (`82bb8af` + `ba505da`)

- **위치**: `pipeline/agents/optimizer/agent.py:166~174` (cold_start 분기) + `prompt.py:43` (SYSTEM_PROMPT 빈 array 분기)
- **시그니처**: `optimize` (agent.py:121)
- **이슈**:
  - git log: `82bb8af feat(report): 4섹션 풍부화 — cold_start LLM 호출`, `ba505da refactor: remove _compose_cold_start_row dead code + dead test`
  - 이전: cases < 3 → `_compose_cold_start_row` placeholder (diagnosis="cold_start", recommendations=[]) → UI 4분면 점 클릭 시 "cold_start" 화면 (사용자 검증 9/22 광건 fab push back)
- **설계 의도**:
  - **cold_start (cases<3) 도 LLM 호출** — `SYSTEM_PROMPT` 의 "degradation_cases 가 빈 array 인 경우" 분기 (prompt.py:43) 활용. 일반적 baseline 관리 권고 3~4건 (모니터링·조기 신호 감지·기록 누적·후행 공정 영향 점검 류) 생성
  - "추측성 회복 패턴 언급은 금지" — recovery_distribution 은 코드단 산출 (이전과 동일)
  - dead code 제거 (`_compose_cold_start_row`) — 분기 단일화
- **대응 패턴**:
  - 입력: 동일 (forecast row + cases — 빈 list 도 OK)
  - 처리: cases 빈 array 도 `_process_one(r, cases)` task 등록 → LLM 응답 받아 `_compose_row`
  - 출력: optimizer_advice row (diagnosis + recommendations 채워짐)
- **관련**:
  - prompt.py SYSTEM_PROMPT 의 빈 array 가이드 (prompt.py:43)
  - 사용자 검증 9/22 광건 fab 사례
- **Suspected related**:
  - `_build_deterministic_cold_start` (view_builder.py:480) — v2 의 cold_start fallback 은 LLM 미사용 (chroma cases 0건일 때만 deterministic)

---

### `_build_productivity_views` (v1) — EVM 산식 4 view

- **위치**: `pipeline/agents/optimizer/view_builder.py:48~76` (entry), `_evm_for_group:79`, `_evm_by_group:161`, `_evm_by_wa_l6_company:238`, `_compose_evm:125`
- **시그니처**: `async def _build_productivity_views(pg, run_id, site_id, today, forecast, mapped) -> dict`
- **이슈**:
  - git log: `2788cfa feat(view_builder): _build_productivity_views + _compose_evm` (초기 2026-05-17), `87d5cbf fix: EVM 산식 컨셉 변경 — 분모=마스터플랜 전체` (2026-05-19)
  - 본 cycle 변경 없음 (산식 자체는 안정), 단 `_evm_by_group` 의 actual anchor (2026-05-20 spec §8.1) 적용 — 매핑된 group 만 표시
- **설계 의도**:
  - EVM 산식 (`_compose_evm` view_builder.py:125): progress = cum_actual_qty / plan_qty_full, EV = progress × plan_mh_full, PV = cum_plan_mh, AC = cum_actual_mh, SPI = EV/PV×100, CPI = EV/AC×100
  - **actual anchor** — `_evm_by_group` (view_builder.py:161~235): plan_agg + actual_agg CTE, `FROM actual_agg a LEFT JOIN plan_agg p USING (gkey)` — plan-only 업체 시연 시 노이즈 제거
  - **wa_l6_company group** — wa 는 mapper 전용 키 → mapper anchor (`_evm_by_wa_l6_company` view_builder.py:238~281)
  - mock row 제외 (`AND ma.is_mock = FALSE`, view_builder.py:203/259)
- **대응 패턴**:
  - 입력: pg, run_id, site_id, today, forecast, mapped (forecast/mapped 는 미사용 — 시그니처 호환)
  - 처리: 4 호출 (today / company / l6_main / wa_l6_company)
  - 출력: `{today, by_contractor, by_l6, by_wp}`
- **관련**:
  - 호출자: `agent.py:187`
  - PG: `activity_master` (plan) + `mapper_activities` (actual)
- **Suspected related**:
  - `_PROGRESS_RATIO_SQL` (view_builder.py:153) — 공통 SQL 상수
  - v2 변형 `_build_productivity_views_v2` — 산식·schema 다름 (이슈 #5)

---

### `_build_quadrant` (v1) — 4분면 분류 (impact P90 normalize)

- **위치**: `pipeline/agents/optimizer/view_builder.py:719~759`
- **시그니처**: `async def _build_quadrant(pg, site_id, today, productivity) -> list[dict]`
- **이슈**:
  - git log: `48e14cd feat(view_builder): _build_quadrant + impact P90` (2026-05-18)
  - 본 cycle 변경 없음 (v2 가 별도 quadrant 산출)
- **설계 의도**:
  - WP 별 산점도 점 (productivity = CPI vs impact = P90 normalize)
  - **impact 정규화**: raw_impact = SUM(plan_total_qty) × AVG(plan_mh) → P90 percentile (len≥10) 또는 max → `min(100, raw/p90×100)`
  - **4분면 label** (`_quadrant_label` view_builder.py:385): low_prod (<80) AND high_impact (≥50) = risk / low_prod = caution / high_impact = watch / safe
  - **size**: `max(30, min(120, int(impact)))` — UI 점 크기 (30~120 px)
- **대응 패턴**:
  - 입력: pg, site_id, today, productivity (`by_wp` 사용)
  - 처리: `mapper_activities` GROUP BY (wa, l6_main, company) → raw_impact + P90 → 각 WP 마다 `_quadrant_label`
  - 출력: `[{wp_id, wp_name, trade, productivity, impact, quadrant, size}, ...]`
- **관련**:
  - 호출자: `agent.py:188`
  - BFF 소비: FE 4분면 산점도 (Layer 2 § 02)
- **Suspected related**:
  - v2 `quadrant` (view_builder.py:1642): share-of-total impact, size = `max(0.1, round(plan_total_qty/10, 1))` — 산식 다름

---

### `_build_optimizer_view` — 4 섹션 진단 + wa fan-out

- **위치**: `pipeline/agents/optimizer/view_builder.py:1024~1129`
- **시그니처**: `def _build_optimizer_view(advice_rows, forecast, mapped, wa_lookup: Optional[dict[tuple[str,str], list[str]]] = None) -> dict`
- **이슈**:
  - git log: `f25d945 feat: _build_optimizer_view — 4 섹션` (초기), `2d98a08 feat: _build_wa_lookup (C4)`, `186042c feat: D2 컨펌 fix — similar_cases schema + actual_trade + today_qty>0`, `bcbdae0 feat: similar_cases description 단순화`, `9176b8d fix: 사용자 4 fix — 라벨 + perperson normalize`
- **설계 의도**:
  - 4 섹션 (Layer 2 § 02 왼쪽): diagnosis / similar_cases / recommendations / details (6 행)
  - **wa fan-out** (view_builder.py:1051~1055, 1124~1126): `wa_list = wa_lookup.get((advice.l6_main, advice.company)) or [matched_f.get("wa")]` → 한 advice 를 wa list 의 각 wa 마다 by_wp 에 복사. quadrant dot 의 wp_id (mapper_activities 기반) 와 매칭 보장 (spec §8.3)
  - **similar_cases description 단순화** (view_builder.py:1058~1078): "생산성 0.52 m/인 (인원 107명)" — main_unit 출처는 matched_f.main_unit
  - **회복분포 풀어쓰기** (`_humanize` view_builder.py:1098~1103): "d+2: 1건" → "2일 후 정상 회복 1건", "not_recovered: 1건" → "미회복 1건"
  - **6 details**: 위험 평가 / 진단 대상 / 유사 사례 수 / 평균 회복 일수 / 회복 분포 / 일정 영향
- **대응 패턴**:
  - 입력: advice_rows, forecast, mapped (미사용 시그니처 호환), wa_lookup
  - 처리: advice 마다 `_match_forecast_by_company_l6` → wa list fan-out → 4 섹션 조립
  - 출력: `{by_wp: {wp_id: {diagnosis, similar_cases, recommendations, details}}, default_wp_id}`
- **관련**:
  - 호출자: `agent.py:213` + v2 `view_builder.py:1783`
  - BFF 소비: `/api/runs/{run_id}/optimizer` (api.py:378)
- **Suspected related**:
  - `_build_wa_lookup` (view_builder.py:409) — fan-out 입력 산출
  - v2 의 T17 quadrant restrict + cold_start fan-out (view_builder.py:1799~1826)

---

### `_compute_recovery_distribution` — 코드단 deterministic Counter

- **위치**: `pipeline/agents/optimizer/agent.py:64~74`
- **시그니처**: `def _compute_recovery_distribution(cases: list[dict]) -> dict[str, int]`
- **이슈**:
  - 결정 #20 (spec §2.6.4): LLM 출력 무시, 코드 값이 정답
  - 본 cycle 변경 없음, 단 `_compose_row` (agent.py:85~98) 가 본 함수 결과로 LLM 출력 override (recovery_distribution 키)
- **설계 의도**:
  - LLM 비결정성 제거 — recovery_days 는 retrieve.py `fetch_recovery_trajectory` 의 결정론 결과 (productivity ≥ baseline×0.95 first day) 만 사용
  - `_build_scenarios` percentile 산출의 input
- **대응 패턴**:
  - 입력: cases (각 case 의 `recovery.recovery_days` 포함)
  - 처리: `Counter([c["recovery"]["recovery_days"] for c in cases])`. `rd is None` → "not_recovered" key
  - 출력: `{"d+1": N, "d+2": N, ..., "not_recovered": N}`
- **관련**:
  - 호출자: `_compose_row` (agent.py:96)
  - 후속: `_build_scenarios` (view_builder.py:1215) — site_days 의 원천
- **Suspected related**:
  - retrieve.py `fetch_recovery_trajectory` — recovery_days 산출 원천

---

### `_call_azure_llm` + `_call_azure_llm_async` — Azure gpt-5.1 호출 (fail-fast, async 변환)

- **위치**: `pipeline/agents/optimizer/agent.py:101~118`
- **시그니처**:
  - `def _call_azure_llm(llm_input, cfg: OptimizerConfig, azure: AzureOpenAI) -> dict`
  - `async def _call_azure_llm_async(llm_input, cfg, azure) -> dict` (asyncio.to_thread wrapper)
- **이슈**:
  - 결정 #10: fail-fast (LLM crash 전체 fail, retry X)
  - git log: `690c305 ★ perf(optimizer): asyncio.gather + to_thread (4×)` — sync 함수를 async 로 감싸 실 병렬
- **설계 의도**:
  - 시연 path 단순화 — LLM 실패 시 cycle 전체 fail (조용한 fallback X)
  - `messages = [SYSTEM_PROMPT, *FEW_SHOT_MESSAGES, user(json.dumps(llm_input))]`
  - `response_format={"type": "json_object"}` 강제 — `json.loads(resp.choices[0].message.content)`
  - `temperature` 박지 않음 (gpt-5 family 미지원 — 결정 #9)
- **대응 패턴**:
  - 입력: llm_input (prompt + cases), cfg, azure client
  - 처리: messages 조립 → Azure gpt-5.1 호출 → JSON parse
  - 출력: dict 또는 Exception
- **관련**:
  - 호출자: `_process_one` (agent.py:159~163, sem 안에서만)
- **Suspected related**:
  - prompt.py SYSTEM_PROMPT / FEW_SHOT_MESSAGES (`build_llm_user_input`)
  - `pipeline.agents._concurrency.get_llm_semaphore` — Azure rate limit 가드

---

### `fetch_recovery_trajectory` — 2-step retrieve Step 2

- **위치**: `pipeline/agents/optimizer/retrieve.py:154~206`
- **시그니처**: `def fetch_recovery_trajectory(metadatas, company, l6_main, case_date, today, baseline_unit, baseline_value, window=7, *, l7_5_activity=None) -> dict`
- **이슈**:
  - 결정 #13: 회복 정의 = productivity ≥ baseline × 0.95 → 첫 ✓까지 일수 (1-based)
  - `l7_5_activity` arg 추가 (phase 2 `f74cdd3`) — 동일 activity 만 매칭하여 case 정합도 상승
- **설계 의도**:
  - case 별 recovery_days 결정 — `_compute_recovery_distribution` input
  - 미회복 → recovery_days=None → distribution 의 "not_recovered" 키
  - window=7 (case_date+1~+7), target_d >= today break (window today clipped)
- **대응 패턴**:
  - 입력: Chroma metadatas, company (None 가능 → cross-company), l6_main, case_date, today, baseline_*, window, *l7_5_activity*
  - 처리: case_date+1 ~ +7 일 productivity 측정 → ≥ baseline×0.95 first day
  - 출력: `{trajectory: [...], recovery_days: int | None}`
- **관련**:
  - 호출자: graph.py `hil_2_node` (graph.py:351~355) — for case in cases loop
  - 페어: `fetch_degradation_cases` — Step 1
- **Suspected related**:
  - `_compute_recovery_distribution` (agent.py:64) — recovery_days 의 indirect 소비

---

### `_group_baseline` — baseline value 산출 (cold_start 분기)

- **위치**: `pipeline/agents/optimizer/retrieve.py:58~88`
- **시그니처**: `def _group_baseline(metadatas, company, l6_main, baseline_unit, *, l7_5_activity=None) -> Optional[float]`
- **이슈**:
  - F7 정정 (spec §8.2): None 분기 명시
  - cold_start signal: baseline_value=None or main_unit=None
- **설계 의도**:
  - 조건 incident 없는 행들의 productivity 평균 (정상 baseline)
  - 데이터 부족 시 None → hil_2_node 에서 `pre_cases[key]=[]` + cold_start payload
- **대응 패턴**:
  - 입력: metadatas (Chroma get 결과), company (None 가능), l6_main, baseline_unit, *l7_5_activity*
  - 처리: filter (l6 + unit + company + l7_5 일치, incident 없음) → `today_qty / assigned_workers` 평균
  - 출력: float 또는 None
- **관련**:
  - 호출자: hil_2_node (graph.py:358~371)
- **Suspected related**:
  - graph.py hil_2_node — None 분기 처리 직접 소비

---

### `generate_synthetic_v2_group` — state machine 7 회복 룰

- **위치**: `pipeline/agents/optimizer/synthetic_v2.py:35` (변경 없음)
- **시그니처**: `def generate_synthetic_v2_group(company, l6_main, activity_pool, baseline_workers, baseline_qty_per_day, unit, days=90, seed=42, reference_date=None) -> list[dict]`
- **이슈**:
  - spec §4.1 7 회복 룰 (장비대기 1d/2d, 우천 연속, 자재미입고, 야간연장, 돌관)
  - 결정 #22: work_content = l7_5_activity 단순 활동명 (조건 텍스트 X)
  - 결정 #19: conditions = comma-joined str
  - 결정성: random.Random(seed) 만 (전역 random 금지)
- **설계 의도**:
  - 90일 synthetic 시계열 → Chroma `daily_activities` 적재
  - 7 룰: 룰 1 장비대기 1일차 × 0.65~0.80, 룰 2 익일 80% 정상/20% 지속, 룰 3 2일차 익일 정상+만회 1.10, 룰 4 우천 2일 후 3일차 1.10, 룰 5 자재미입고 익일 50/50, 룰 6 야간연장 fatigue 0.90, 룰 7 돌관 0.85 + workers 1.3 spike
  - `_BP_TOTAL` (synthetic_v2.py:28) — `{"남웅건설": 88, "세보엠이씨": 1387, "창원기전": 372}`
- **대응 패턴**:
  - 입력: company, l6_main, activity_pool, baseline_*, days, seed, reference_date
  - 처리: state machine 90일 loop, 7 회복 룰 random.Random(seed) 적용
  - 출력: list[dict] (date, company, l6_main, unit, today_qty, assigned_workers, conditions, work_content, worker_source="synthetic_v2")
- **관련**:
  - 호출자: CLI (`python -m pipeline.agents.optimizer.synthetic_v2`)
  - PG 입력: `activity_master` → 27 그룹 main_unit + activity_pool + total_qty + total_mh
  - Chroma 출력: `daily_activities` collection (worker_source="synthetic_v2"), Azure embedding `text-embedding-3-small` batch=16
- **Suspected related**:
  - `_BP_TOTAL` (synthetic_v2.py:28)
  - `scripts/seed_dummy_year.py` — 같은 산식 530일 적용 (F3 piecewise / prod 90% 역산 / l5_disc / today_conditions metadata)

---

### `generate_fake_daily_report` — Demo Activity 직접 생성

- **위치**: `pipeline/agents/optimizer/synthetic_daily_report.py:50` (변경 없음)
- **시그니처**: `def generate_fake_daily_report(report_date, scenarios, activity_pools, baseline_workers, baseline_qty, seed) -> list[Activity]`
- **이슈**:
  - spec §10.2: Activity list 직접 생성 (Parser/Mapper skip)
  - conditions = list[str] (mapper 호환)
- **설계 의도**:
  - synthetic_daily_report.py CLI 의 input — build_demo_graph 진입
  - 데모 시연용 (forecaster → hil_2 → optimizer → reporter 경로)
- **대응 패턴**:
  - 입력: report_date, scenarios (n개), activity_pools, baseline_*, seed
  - 처리: scenarios iteration, 각 scenario 마다 n_activities random.Random(seed) 생성
  - 출력: list[Activity] (mapper 호환)
- **관련**:
  - 호출자: synthetic_daily_report.py `_main_cli` (synthetic_daily_report.py:355~493) 9 step CLI
  - graph: `build_demo_graph(cfg).ainvoke(...)` → `__interrupt__` payload → `--auto-select-all` flag 자동 resume → advice 출력
- **Suspected related**:
  - `_initial_state` (synthetic_daily_report.py:242)
  - `build_demo_graph_config`

---

## 변경 사항 정리 (cf3c143..1ba783f, optimizer 관련 25+ commits)

| Commit | 날짜 | 변경 |
|---|---|---|
| 2788cfa | 2026-05-17 | feat: _build_productivity_views + _compose_evm (EVM core 초기) |
| b20549d | 2026-05-18 | feat: _build_kpi + bars |
| 48e14cd | 2026-05-18 | feat: _build_quadrant + impact P90 |
| 42bc99a | 2026-05-18 | feat: _build_s_curve + _merge_curves + _extend_forecast |
| f25d945 | 2026-05-18 | feat: _build_optimizer_view — 4 섹션 |
| 7fa3dd9 | 2026-05-18 | feat(optimizer): build view jsonb + daily_reports UPSERT + state.site_id |
| e432dc2 | 2026-05-18 | feat: _evm_by_group 구현 (group_key 다형성) |
| 64318f6 | 2026-05-18 | feat(backfill): daily_report_views 기존 cycle 채움 |
| c404086 | 2026-05-19 | fix: _evm_for_group plan scope actual scope |
| 82ca0b4 | 2026-05-19 | fix: _evm_for_group mapped CTE filter |
| 87d5cbf | 2026-05-19 | fix: EVM 산식 컨셉 변경 — 분모=마스터플랜 전체 |
| 3781e5b | 2026-05-19 | ★ feat: _build_scenarios + scenarios_jsonb upsert |
| 105ee6a | 2026-05-19 | fix: review feedback — recovery wiring + e2e negative + date coerce |
| 38127ff | 2026-05-21 | ★ feat: _build_productivity_views_v2 통합 산식 (Task 9) |
| adac813 | 2026-05-21 | feat: _augment_history_if_sparse (C7, Task 10) |
| f46e47e | 2026-05-21 | feat(optimizer): cold_start 라벨 + augmentation weight (C9, Task 11) |
| 556d4da | 2026-05-21 | feat(backfill): 530일 view_builder_v2 + idempotent seed |
| a8081b2 | 2026-05-22 | feat: view_builder wp_id 통일 + quadrant 키 4개 + SELECT wa/today_qty (C2) |
| 3271378 | 2026-05-22 | feat: view_builder return 9 key stub (C3) |
| 2d98a08 | 2026-05-22 | feat: _build_wa_lookup (C4) |
| c67f341 | 2026-05-22 | feat: _build_deterministic_cold_start + 8 cause + 5 rule (C5) |
| 3029653 | 2026-05-22 | feat: _fetch_chroma_cases_lookup 3단 fallback (C6) |
| 5d69a2f | 2026-05-22 | feat: _build_optimizer_view 통합 + cold_start 채움 + jsonb inflate (C7) |
| 450c9a7 | 2026-05-22 | feat: scenarios + s_curve 기존 함수 호출 + integration test (C8) |
| f74cdd3 | 2026-05-22 | feat: retrieve.py 3 함수 l7_5_activity arg (C9) |
| 186042c | 2026-05-22 | feat: D2 컨펌 fix — similar_cases schema + actual_trade + today_qty>0 |
| 98d844d | 2026-05-22 | feat: chroma_cases_lookup 에 worker_source='backfill_v2' filter |
| bcbdae0 | 2026-05-22 | feat: similar_cases description 단순화 (perperson 만) |
| 739b2cd | 2026-05-22 | feat: _pick_recommendations R5 단순화 (pct >= 90 → 정상 페이스) |
| 8fe28b2 | 2026-05-22 | fix: WBS 트리 am_combos l5_disc 필터 + chroma sort by date |
| d8ad216 | 2026-05-22 | fix: chroma_cases_lookup col.get limit 50 (httpx timeout 회피) |
| c9c64b8 | 2026-05-22 | fix: review 트리 마스터 전체 + WP 중복 group by |
| 72dd7f2 | 2026-05-22 | fix: ChromaClient module-level singleton (530일 socket 누적 timeout) |
| 9176b8d | 2026-05-22 | fix: 사용자 4 fix — 라벨 + perperson normalize + review today_qty>0 |
| 4b67340 | 2026-05-23 | fix: dashboard 자릿수 + 유사사례 0 exclude + 공기단축 라벨 통일 |
| ccefd30 | 2026-05-23 | fix: WP 목록 impact desc 정렬 |
| 2074fd6 | 2026-05-23 | fix: UI ↔ BE 숫자 매핑 정합화 7건 |
| 10b4176 | 2026-05-23 | feat(forecast): 공기 단축 시나리오 catch-up 시각화 + LLM 권고 narrative |
| **c0a0641** | **2026-05-24** | **★★ feat(view-builder): 공정률 산식 재설계 — WV × MH 가중 + activity 매칭** |
| **21c10f7** | **2026-05-24** | **★★ feat(site-summary): Optimizer LLM 산출 site 수준 narrative + FE 룰베이스 교체** |
| **82bb8af** | **2026-05-24** | **feat(report): 4섹션 풍부화 — retrieve 완화 + delay qty 산식 + cold_start LLM** |
| ba505da | 2026-05-24 | refactor: remove _compose_cold_start_row dead code + dead test |
| 811a408 | 2026-05-24 | test(t1.5): review fix-up |
| **690c305** | **2026-05-24** | **★ perf(optimizer): optimize() forecast 루프 asyncio.gather + to_thread (4×)** |
| **2c2ba75** | **2026-05-25** | **★ fix: T17 quadrant ↔ by_wp wp_id 매칭 보강 (Jaccard 11% → 100%)** |
| **e9b66d4** | **2026-05-25** | **★ fix(view_builder): site KPI delay_days AVG -> MEDIAN (outlier 167,871일 → 11일)** |
| **d79a438** | **2026-05-25** | **★ feat(retrieve): incident keyword 9종 보강 (5 → 9)** |
| ffcef7b | 2026-05-25 | feat: backfill_optimizer_advice_llm.py 일반화 |

---

## 설계 결정 (spec 2026-05-16 의 21 결정 중 핵심)

| # | 결정 | 위치 |
|---|---|---|
| #8 | pre_optimizer_cases 사전 영속 (retrieve 재호출 X) | graph.py hil_2_node |
| #9 | temperature 박지 않음 (gpt-5 family 미지원) | agent.py `_call_azure_llm` |
| #10 | fail-fast (LLM crash 전체 fail) | agent.py `_call_azure_llm` |
| #11 | ~~cold_start < 3 cases → LLM skip~~ → **본 cycle 변경 (`82bb8af`)**: cases<3 도 LLM 호출 | agent.py:171~174 코멘트 |
| #13 | recovery ≥ baseline × 0.95 | retrieve.py `fetch_recovery_trajectory` |
| #14 | ~~degradation ∋ incident **∧** < baseline × 0.85~~ → **본 cycle 변경 (`82bb8af`)**: OR 완화 + worker_source 화이트리스트 제거 | retrieve.py:136~140 |
| #19 | conditions = comma-joined str | retrieve.py / synthetic_v2 통일 |
| #20 | recovery_distribution = 코드단 Counter (LLM override) | agent.py `_compute_recovery_distribution` |
| #22 | work_content = 단순 활동명 (조건 텍스트 X) | synthetic_v2.py |

---

## 이슈 표 (10 건, deep_dive 발견)

| # | 이슈 | 위치 | 영향 | 우선순위 |
|---|---|---|---|---|
| **1** | **working tree 미커밋 1 줄** — `AND ma.trade IN ('건축', '토목')` 제거 (다른 세션) | view_builder.py:1447 | v2 산출 대상 확장 (설비/전기 등 포함). 9 jsonb 산식 변동 가능 | **즉시 — 다른 세션 작업과 충돌 가능** |
| **2** | **`Optional` 미 import** — `from typing import Any` 만 있고 `Optional` 부재 | view_builder.py:399/481/594/1028/1093, agent.py:128/129 | `from __future__ import annotations` 덕에 런타임 OK. `typing.get_type_hints()` 호출 시 NameError | 낮음 — 잠재 latent |
| **3** | **site_summary 가 production 그래프 미연결** | site_summary.py + scripts/backfill_daily_report_views_v2.py:141 만 호출 | live `optimize()` 실행 시 `daily_reports.site_summary_text` 비어있음. FE narrative 미표시 | 중간 — backfill 의존 |
| **4** | **`_normalize_impact` vs `_normalize_impact_share` 이름 충돌** | view_builder.py:378 vs 1331 | shadowing 위험 — 함수 시그니처 (1 arg vs 2 arg) 로 분리되어 현재 안전. 코멘트 (view_builder.py:1337) 박혀 있음 | 모니터 |
| **5** | **v1 `_build_productivity_views` ↔ v2 `_build_productivity_views_v2` 병행** | view_builder.py:48 vs 1410 | `agent.py:187` 은 v1 호출, `backfill_daily_report_views_v2.py:125` 는 v2 호출. 산식·schema 다름 → 같은 컬럼 (productivity_jsonb) 다른 산식 → drift 위험 #N19 | **중간 — 통합 또는 deprecation 결정 필요** |
| **6** | **RAG fixture vs synthetic_v2 baseline ±10% drift** | retrieve.py 매칭 + synthetic_v2 generation seed 변경 | recovery_distribution 수치 변동 → scenarios percentile 변동 → KPI recovery_days 변동 | 모니터 |
| **7** | **v1 cold_start (`_build_deterministic_cold_start`) 의 `productivity` 키 scale 혼합** | view_builder.py:489 `q.get("productivity")` | quadrant item 의 productivity (v1=CPI 0~150, v2=인당/마스터 0~150) scale 다름. v2 cold_start 시 q["productivity"] = 0~150 의 v2 산식 | 모니터 — v1/v2 혼용 시 |
| **8** | **`_evm_by_wa_l6_company` 의 LEFT JOIN am** | view_builder.py:254~257 | mapper anchor — wa 가 plan side 에 없으면 plan 0. EVM CPI NaN 가능 | 표시 fallback ("—") 처리 |
| **9** | **`_get_all_backfill_metas` 캐시 무효화 없음** | view_builder.py:611 | 모듈 캐시 (`_chroma_metas_cache`) 가 process lifetime. backfill 도중 새 row 적재해도 미반영 | 낮음 — 단일 실행 가정 |
| **10** | **`build_demo_graph` 와 production `build_graph` 의 mapped state 차이** | synthetic_daily_report.py:411 mapped 직접 주입 vs production Mapper 노드 산출 | mapped 형식 drift 시 view_builder 산식 (특히 `_build_optimizer_view` wa fan-out) 깨질 수 있음 | 컨트랙트 테스트 권장 |

---

## 미해결 / Backlog

- **v1 ↔ v2 산식 일원화** — 이슈 #5. agent.py 가 v2 호출하도록 마이그 or v1 deprecation 결정 필요. 같은 컬럼 `productivity_jsonb` 두 산식 (EVM vs 인당) 운용은 시연 핵심 지표 일관성에 위험.
- **site_summary production wiring** — 이슈 #3. `optimize()` 끝에 `build_site_summary_payload + generate_site_summary + UPDATE` 추가하여 live path 도 narrative 채움.
- **working tree 1 줄 (이슈 #1)** — `view_builder.py:1447` `AND ma.trade IN ('건축', '토목')` 제거. 커밋 또는 revert 결정 필요 (다른 세션 작업).
- **`Optional` import (이슈 #2)** — `view_builder.py` + `agent.py` 두 곳 `from typing import Any, Optional` 로 변경.
- **EVM 산식 반복** — `_compose_evm` 패턴이 `_evm_for_group` / `_evm_by_group` / `_evm_by_wa_l6_company` 에서 반복, 제네릭 aggregation fn 추상화 검토.
- **view_builder 함수 밀도 (45 함수, 7 phase)** — 향후 섹션별 모듈 분리 검토 (kpi.py / quadrant.py / s_curve.py / v2.py).
- **scenarios 시나리오명 i18n** — no_action/optimistic_p25/base_p50/pessimistic_p75 영문 고정. 라벨↔분위수 swap 의도 (view_builder.py:1237~1241) 가 코드 주석에만 박혀 있음 — FE 표시 라벨과 산식 의미 분리 문서화 필요.
- **MEDIAN SQL 중복** — view_builder.py:295~309 + 1693~1706 두 곳 동일 PERCENTILE_CONT/DISC. 헬퍼 추출.
