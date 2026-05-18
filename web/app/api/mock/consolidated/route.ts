// /api/mock/consolidated
//   ?date 없음     → 최근 7일치 ConsolidatedReportSummary[]
//   ?date=YYYY-MM-DD → 단건 ConsolidatedReport (4 시트 raw rows 포함)
// 결정적 PRNG (mulberry32 + YYYYMMDD seed). agent-tasks 라우트와 동일 패턴.
// A_Track 의 staging 테이블 + GET 엔드포인트가 준비되면 fetch URL 만 swap.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import type {
  ConsolidatedReport,
  ConsolidatedReportSummary,
  OutputManpowerRow,
  OccupationManpowerRow,
  EquipmentRow,
  QuantityRow,
} from "@/lib/types";

const BASE = "2026-05-15";
const DAYS = 7;
const PJT  = "M15X Ph-3 IBL";

// 엑셀 4 시트에서 발췌
const BPS: Array<[string, string]> = [
  ["PH_X-002", "㈜에스티엠"],
  ["PH_X-003", "㈜아스타아이비에스"],
  ["PH_X-011", "㈜거성씨엔에스"],
  ["PH_X-015", "㈜청조이엔씨"],
  ["PH_X-046", "(주)캠파트너스"],
  ["PH_X-082", "㈜거성씨엔에스F03"],
  ["PH_X-088", "㈜해광FAB"],
  ["PH_X-117", "한국방재기술"],
];

const ZONES  = ["FAB", "CUB", "FAB/CUB", "F02", "F03", "F04"] as const;
const TRADES = [
  "공통가설", "토공사", "철근공사", "거푸집공사", "콘크리트공사",
  "방수공사", "전기공사", "기계설비", "소방설비", "마감공사",
] as const;

const SCOPES = ["지원관앞", "M15 X FAB", "FAB 전구간", "F02 1F", "F03 2F", "F04 3F", "CUB 옥상"];

const WORK_TEMPLATES = [
  "현장 점검 및 안전순찰",
  "M15 X FAB F02 1F C/R 환경관리",
  "FAB F03 2F C/R 청정관리",
  "F02 슈퍼데크 설치",
  "임시스막룸 운영",
  "FAB 호이스트 운행",
  "DCC 구간 대청소",
  "외곽 환경유지관리",
  "X 동문 게이트 및 교통 통제",
  "우천 대응관련작업",
];

const OCCUPATIONS = [
  "BP소장", "공사관리자", "안전관리자", "품질관리자", "일반관리자",
  "철근공", "형틀목공", "콘크리트공", "미장공", "조적공",
  "전공", "배관공", "용접공", "도장공", "건축철물공",
];

const EQUIPMENTS: Array<[string, string, string]> = [
  ["굴삭운반기계류", "Back Hoe",   "2㎥ 미만"],
  ["굴삭운반기계류", "Back Hoe",   "2㎥ 이상~5㎥ 미만"],
  ["굴삭운반기계류", "굴삭기",      "3LC"],
  ["굴삭운반기계류", "굴삭기",      "6LC"],
  ["크레인",         "타워크레인",  "T-200"],
  ["크레인",         "이동식크레인", "50ton"],
  ["크레인",         "이동식크레인", "25ton"],
  ["운반기계류",      "지게차",      "3ton"],
  ["콘크리트장비",    "콘크리트펌프카", "60㎥/h"],
  ["용접장비",       "엔진용접기",   "300A"],
];

const UNITS = ["EA", "㎡", "㎥", "ton", "m"];

// ────── PRNG ──────
function mulberry32(seed: number) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function seedFromDate(s: string): number {
  return parseInt(s.replace(/-/g, ""), 10);
}
function pick<T>(rnd: () => number, arr: readonly T[]): T {
  return arr[Math.floor(rnd() * arr.length)];
}
function ri(rnd: () => number, lo: number, hi: number): number {
  return lo + Math.floor(rnd() * (hi - lo + 1));
}
function dateOffset(baseISO: string, daysAgo: number): string {
  const d = new Date(baseISO + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - daysAgo);
  return d.toISOString().slice(0, 10);
}

// ────── 시트별 generator ──────
function genOutputManpower(rnd: () => number, n: number): OutputManpowerRow[] {
  const out: OutputManpowerRow[] = [];
  for (let i = 0; i < n; i++) {
    const [bp_code] = pick(rnd, BPS);
    const work = pick(rnd, WORK_TEMPLATES);
    out.push({
      pjt: "M15X",
      zone: pick(rnd, ZONES),
      trade: pick(rnd, TRADES),
      bp_code,
      scope: pick(rnd, SCOPES),
      main_work: work,
      prev_work: work,
      today_work: work,
      next_work: work,
      early: ri(rnd, 0, 8),
      day: ri(rnd, 5, 90),
      overtime: ri(rnd, 0, 25),
    });
  }
  return out;
}

function genOccupationManpower(rnd: () => number, n: number): OccupationManpowerRow[] {
  const out: OccupationManpowerRow[] = [];
  for (let i = 0; i < n; i++) {
    const [bp_code] = pick(rnd, BPS);
    const idx = i + 1;
    const day = ri(rnd, 0, 30);
    const overtime = ri(rnd, 0, 8);
    out.push({
      trade: pick(rnd, TRADES),
      bp_code,
      manager_code: `Mm${String(idx).padStart(2, "0")}`,
      skilled_code: `sk${String(idx).padStart(2, "0")}`,
      occupation: pick(rnd, OCCUPATIONS),
      prev_cum: ri(rnd, 0, 50),
      early: ri(rnd, 0, 3),
      day,
      overtime,
      night: ri(rnd, 0, 2),
      allnight: ri(rnd, 0, 1),
      cum_t: day + overtime + ri(rnd, 0, 10),
    });
  }
  return out;
}

function genEquipment(rnd: () => number, n: number): EquipmentRow[] {
  const out: EquipmentRow[] = [];
  for (let i = 0; i < n; i++) {
    const [bp_code] = pick(rnd, BPS);
    const [eq_major, eq_mid, eq_spec] = pick(rnd, EQUIPMENTS);
    const day = ri(rnd, 0, 8);
    out.push({
      trade: pick(rnd, TRADES),
      bp_code,
      eq_major, eq_mid, eq_spec,
      prev_cum: ri(rnd, 0, 20),
      early: ri(rnd, 0, 2),
      day,
      overtime: ri(rnd, 0, 3),
      night: 0,
      allnight: 0,
      cum_t: day + ri(rnd, 0, 5),
    });
  }
  return out;
}

function genQuantity(rnd: () => number, n: number): QuantityRow[] {
  const out: QuantityRow[] = [];
  for (let i = 0; i < n; i++) {
    const [bp_code, bp_name] = pick(rnd, BPS);
    const total = ri(rnd, 30, 500);
    const prev  = Math.min(total, ri(rnd, 0, Math.round(total * 0.7)));
    const today = ri(rnd, 0, Math.max(1, Math.round(total * 0.2)));
    out.push({
      zone: pick(rnd, ZONES),
      trade: pick(rnd, TRADES),
      bp_code,
      bp_name,
      scope: "M15-Ph-X FAB/CUB",
      rep_work: pick(rnd, WORK_TEMPLATES),
      unit: pick(rnd, UNITS),
      total_a: total,
      prev_cum_b: prev,
      today_c: today,
    });
  }
  return out;
}

// ────── 일자별 단건 보고서 ──────
function generateReport(date: string, daysAgo: number): ConsolidatedReport {
  const rnd = mulberry32(seedFromDate(date));
  const om_n = ri(rnd, 12, 18);
  const oc_n = ri(rnd, 30, 50);
  const eq_n = ri(rnd, 20, 35);
  const q_n  = ri(rnd, 15, 25);

  const output_manpower      = genOutputManpower(rnd, om_n);
  const occupation_manpower  = genOccupationManpower(rnd, oc_n);
  const equipment            = genEquipment(rnd, eq_n);
  const quantity             = genQuantity(rnd, q_n);

  return {
    date,
    pjt: PJT,
    status: daysAgo === 0 ? "draft" : "ready",
    sheet_row_counts: {
      output_manpower: om_n,
      occupation_manpower: oc_n,
      equipment: eq_n,
      quantity: q_n,
    },
    output_manpower,
    occupation_manpower,
    equipment,
    quantity,
  };
}

function summary(report: ConsolidatedReport): ConsolidatedReportSummary {
  return {
    date: report.date,
    pjt: report.pjt,
    status: report.status,
    sheet_row_counts: report.sheet_row_counts,
  };
}

// ────── route handler ──────
export async function GET(req: Request) {
  const url = new URL(req.url);
  const date = url.searchParams.get("date");

  if (date) {
    const daysAgo = Math.max(
      0,
      Math.round(
        (new Date(BASE + "T00:00:00Z").getTime() -
          new Date(date + "T00:00:00Z").getTime()) /
          86_400_000
      )
    );
    return NextResponse.json(generateReport(date, daysAgo));
  }

  const list: ConsolidatedReportSummary[] = [];
  for (let i = 0; i < DAYS; i++) {
    const d = dateOffset(BASE, i);
    list.push(summary(generateReport(d, i)));
  }
  return NextResponse.json(list);
}
