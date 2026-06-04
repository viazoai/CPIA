// /api/mock/consolidated — A_Track PG 직접 SELECT 로 swap (Task 5.6).
//   ?date 없음     → ConsolidatedReportSummary[] (1년 윈도우, pipeline_runs.report_date distinct).
//   ?date=YYYY-MM-DD → 단건 ConsolidatedReport (4 시트 raw rows).
//
// 정규화 테이블 parser_job_allocations / parser_equipment_allocations 는 현재 비어 있어,
// 모든 시트 raw 는 parser_reports jsonb 컬럼 (bp_summaries / job_allocations / equipment_allocations)
// 과 parser_activities 에서 가져온다.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type {
  ConsolidatedReport,
  ConsolidatedReportSummary,
  OutputManpowerRow,
  OccupationManpowerRow,
  EquipmentRow,
  QuantityRow,
} from "@/lib/types";
import {
  outputFromBpSummaries,
  reconstructOutputFromMapper,
  bpLabel,
  type MapperOutputAgg,
} from "@/lib/consolidated-transforms";

const PJT = "M15X Ph-3 IBL";

function toDateStr(d: Date | string): string {
  if (typeof d === "string") return d.slice(0, 10);
  return d.toISOString().slice(0, 10);
}

function asArray(v: unknown): any[] {
  if (Array.isArray(v)) return v;
  if (typeof v === "string") {
    try {
      const p = JSON.parse(v);
      return Array.isArray(p) ? p : [];
    } catch {
      return [];
    }
  }
  return [];
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const date = searchParams.get("date");
  const useMock = process.env.CPIA_DEMO_FALLBACK === "on";

  // ────── 일자 리스트 — 단일 CTE 로 N+1 제거 ──────
  if (!date) {
    // latest_reports: 같은 (date) 의 parser_reports 중 최신 created_at 만 → jsonb_array_length.
    // act_counts: 날짜별 parser_activities 총건수.
    const rows = (await (sql as any)`
      WITH latest_reports AS (
        SELECT DISTINCT ON (report_date)
          report_date,
          jsonb_array_length(bp_summaries) AS output_count,
          jsonb_array_length(job_allocations) AS occupation_count,
          jsonb_array_length(equipment_allocations) AS equipment_count
        FROM parser_reports
        WHERE report_date >= CURRENT_DATE - INTERVAL '1 year'
          AND is_mock = ${useMock}
        ORDER BY report_date DESC, created_at DESC
      ),
      act_counts AS (
        SELECT pr.report_date, COUNT(*)::int AS quantity_count
        FROM parser_activities pa
        JOIN pipeline_runs pr USING (run_id)
        WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
          AND pa.is_mock = ${useMock}
        GROUP BY pr.report_date
      ),
      run_dates AS (
        SELECT DISTINCT report_date
        FROM pipeline_runs
        WHERE report_date >= CURRENT_DATE - INTERVAL '1 year'
          AND is_mock = ${useMock}
      )
      SELECT rd.report_date,
             COALESCE(lr.output_count, 0)      AS output_count,
             COALESCE(lr.occupation_count, 0)  AS occupation_count,
             COALESCE(lr.equipment_count, 0)   AS equipment_count,
             COALESCE(ac.quantity_count, 0)    AS quantity_count
      FROM run_dates rd
      LEFT JOIN latest_reports lr USING (report_date)
      LEFT JOIN act_counts ac USING (report_date)
      ORDER BY rd.report_date DESC
      LIMIT 365
    `) as Array<{
      report_date: Date | string;
      output_count: number;
      occupation_count: number;
      equipment_count: number;
      quantity_count: number;
    }>;

    const summaries: ConsolidatedReportSummary[] = rows.map((r) => ({
      date: toDateStr(r.report_date),
      pjt: PJT,
      status: "ready",
      sheet_row_counts: {
        output_manpower: r.output_count,
        occupation_manpower: r.occupation_count,
        equipment: r.equipment_count,
        quantity: r.quantity_count,
      },
    }));
    return NextResponse.json(summaries, {
      headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
    });
  }

  // ────── 단건 detail — 4 시트 raw ──────
  const reportRows = (await (sql as any)`
    SELECT bp_summaries, job_allocations, equipment_allocations
    FROM parser_reports
    WHERE report_date = ${date}
      AND is_mock = ${useMock}
    ORDER BY created_at DESC
    LIMIT 1
  `) as Array<{
    bp_summaries: unknown;
    job_allocations: unknown;
    equipment_allocations: unknown;
  }>;
  const bp_summaries = asArray(reportRows[0]?.bp_summaries);
  const job_allocations = asArray(reportRows[0]?.job_allocations);
  const equipment_allocations = asArray(reportRows[0]?.equipment_allocations);

  const acts = (await (sql as any)`
    SELECT pa.zone, pa.trade, pa.bp_code, pa.company, pa.scope,
           pa.work_content, pa.unit, pa.plan_total_qty, pa.yesterday_cum_qty, pa.today_qty,
           ma.wa AS mapper_wa
    FROM parser_activities pa
    JOIN pipeline_runs pr USING (run_id)
    LEFT JOIN mapper_activities ma USING (run_id, idx)
    WHERE pr.report_date = ${date}
      AND pa.is_mock = ${useMock}
  `) as Array<{
    zone: string | null;
    trade: string | null;
    bp_code: string | null;
    company: string | null;
    scope: string | null;
    work_content: string | null;
    unit: string | null;
    plan_total_qty: number | string | null;
    yesterday_cum_qty: number | string | null;
    today_qty: number | string | null;
    mapper_wa: string | null;
  }>;

  // 시트1 zone 소스: mapper_activities.wa 를 회사별 최빈값으로 집계.
  // bp_summaries jsonb 에는 idx 가 없어 직접 JOIN 불가 → company 기준 대표 wa 사용.
  const waRows = (await (sql as any)`
    SELECT ma.company, ma.wa, COUNT(*)::int AS cnt
    FROM mapper_activities ma
    JOIN pipeline_runs pr USING (run_id)
    WHERE pr.report_date = ${date}
      AND ma.is_mock = ${useMock}
      AND COALESCE(ma.wa, '') <> ''
    GROUP BY ma.company, ma.wa
  `) as Array<{ company: string; wa: string; cnt: number }>;

  // 회사별 최빈 wa: 동점 시 FAB 우선, 그 외는 사전순 역순(결정론적).
  const companyWa: Record<string, string> = {};
  const waByCo: Record<string, Array<{ wa: string; cnt: number }>> = {};
  for (const r of waRows) {
    if (!waByCo[r.company]) waByCo[r.company] = [];
    waByCo[r.company].push({ wa: r.wa, cnt: r.cnt });
  }
  for (const [company, entries] of Object.entries(waByCo)) {
    const maxCnt = Math.max(...entries.map((e) => e.cnt));
    const tied = entries.filter((e) => e.cnt === maxCnt);
    if (tied.some((e) => e.wa === "FAB")) {
      companyWa[company] = "FAB";
    } else {
      // 사전순 역순 중 첫 번째 (결정론적)
      tied.sort((a, b) => b.wa.localeCompare(a.wa));
      companyWa[company] = tied[0].wa;
    }
  }

  // 시트1 — bp_summaries 있으면 그대로(BP사=업체명), 없으면(시드일) mapper per-company 재구성.
  let output_manpower: OutputManpowerRow[];
  if (bp_summaries.length > 0) {
    output_manpower = outputFromBpSummaries(bp_summaries, companyWa);
  } else {
    const outAgg = (await (sql as any)`
      SELECT ma.company,
             MAX(ma.trade)                                       AS trade,
             SUM(COALESCE(ma.assigned_workers, 0))::float        AS workers_total,
             string_agg(DISTINCT NULLIF(pa.work_content, ''), E'\n') AS work_today
      FROM mapper_activities ma
      LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
      WHERE ma.report_date = ${date}
        AND ma.is_mock = ${useMock}
        AND ma.trade IN ('건축', '토목')
      GROUP BY ma.company
      ORDER BY ma.company
    `) as MapperOutputAgg[];
    output_manpower = reconstructOutputFromMapper(outAgg, companyWa);
  }

  // 시트2 — 직종별 인원: parser_reports.job_allocations jsonb 펼침.
  const occupation_manpower: OccupationManpowerRow[] = job_allocations.map((j: any) => ({
    trade: String(j.disc_abbrev ?? ""),
    bp_code: bpLabel(j.company, j.bp_code),
    manager_code: String(j.manager_code ?? ""),
    skilled_code: String(j.worker_code ?? ""),
    occupation: String(j.job_type ?? ""),
    prev_cum: 0,
    early: 0,
    day: 0,
    overtime: 0,
    night: 0,
    allnight: 0,
    cum_t: Number(j.workers_cum_t ?? 0),
  }));

  // 시트3 — 장비: parser_reports.equipment_allocations jsonb 펼침.
  const equipment: EquipmentRow[] = equipment_allocations.map((e: any) => ({
    trade: String(e.disc_abbrev ?? ""),
    bp_code: bpLabel(e.company, e.bp_code),
    eq_major: String(e.equipment_big ?? ""),
    eq_mid: String(e.equipment_mid ?? ""),
    eq_spec: String(e.equipment_spec ?? ""),
    prev_cum: 0,
    early: 0,
    day: 0,
    overtime: 0,
    night: 0,
    allnight: 0,
    cum_t: Number(e.count_cum_t ?? 0),
  }));

  // 시트4 — 물량: mapper_activities.wa 우선, 없으면 parser_activities.zone 폴백.
  const quantity: QuantityRow[] = acts.map((a) => ({
    zone: a.mapper_wa ?? a.zone ?? "",
    trade: a.trade ?? "",
    bp_code: a.bp_code ?? "",
    bp_name: a.company ?? "",
    scope: a.scope ?? "",
    rep_work: a.work_content ?? "",
    unit: a.unit ?? "",
    total_a: a.plan_total_qty != null ? Number(a.plan_total_qty) : 0,
    prev_cum_b: a.yesterday_cum_qty != null ? Number(a.yesterday_cum_qty) : 0,
    today_c: a.today_qty != null ? Number(a.today_qty) : 0,
  }));

  const report: ConsolidatedReport = {
    date,
    pjt: PJT,
    status: "ready",
    sheet_row_counts: {
      output_manpower: output_manpower.length,
      occupation_manpower: occupation_manpower.length,
      equipment: equipment.length,
      quantity: quantity.length,
    },
    output_manpower,
    occupation_manpower,
    equipment,
    quantity,
  };
  return NextResponse.json(report, {
    headers: { "Cache-Control": "s-maxage=30, stale-while-revalidate=60" },
  });
}
