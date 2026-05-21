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

  // ────── 일자 리스트 ──────
  if (!date) {
    const dates = (await (sql as any)`
      SELECT DISTINCT pr.report_date
      FROM pipeline_runs pr
      WHERE pr.report_date >= CURRENT_DATE - INTERVAL '1 year'
        AND pr.is_mock = ${useMock}
        AND pr.site_id = 'm15x-ph3-ibl'
      ORDER BY pr.report_date DESC
      LIMIT 365
    `) as Array<{ report_date: Date | string }>;

    const summaries: ConsolidatedReportSummary[] = [];
    for (const { report_date } of dates) {
      const dStr = toDateStr(report_date);
      const counts = (await (sql as any)`
        SELECT
          COALESCE((
            SELECT jsonb_array_length(bp_summaries)
            FROM parser_reports WHERE report_date = ${dStr} AND is_mock = ${useMock}
            ORDER BY created_at DESC LIMIT 1
          ), 0) AS output_count,
          COALESCE((
            SELECT jsonb_array_length(job_allocations)
            FROM parser_reports WHERE report_date = ${dStr} AND is_mock = ${useMock}
            ORDER BY created_at DESC LIMIT 1
          ), 0) AS occupation_count,
          COALESCE((
            SELECT jsonb_array_length(equipment_allocations)
            FROM parser_reports WHERE report_date = ${dStr} AND is_mock = ${useMock}
            ORDER BY created_at DESC LIMIT 1
          ), 0) AS equipment_count,
          (
            SELECT COUNT(*)
            FROM parser_activities pa
            JOIN pipeline_runs pr USING (run_id)
            JOIN mapper_activities ma ON ma.run_id = pa.run_id AND ma.idx = pa.idx
            WHERE pr.report_date = ${dStr}
              AND pa.is_mock = ${useMock}
              AND ma.trade IN ('건축', '토목')
          ) AS quantity_count
      `) as Array<Record<string, number | string | null>>;
      const c = counts[0] ?? {};
      summaries.push({
        date: dStr,
        pjt: PJT,
        status: "ready",
        sheet_row_counts: {
          output_manpower: Number(c.output_count ?? 0),
          occupation_manpower: Number(c.occupation_count ?? 0),
          equipment: Number(c.equipment_count ?? 0),
          quantity: Number(c.quantity_count ?? 0),
        },
      });
    }
    return NextResponse.json(summaries);
  }

  // ────── 단건 detail — 4 시트 raw ──────
  // disc_abbrev 가 PG 데이터에 모두 null — 필터 제거 (RC4 의도는 탭 이름 + 컬럼 숨김).
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
    SELECT COALESCE(NULLIF(pa.zone, ''), split_part(ma.wa, '-', 1), '—') AS zone,
           pa.trade, pa.bp_code, pa.company, pa.scope,
           pa.work_content, pa.unit, pa.plan_total_qty, pa.yesterday_cum_qty, pa.today_qty
    FROM parser_activities pa
    JOIN pipeline_runs pr USING (run_id)
    JOIN mapper_activities ma ON ma.run_id = pa.run_id AND ma.idx = pa.idx
    WHERE pr.report_date = ${date}
      AND pa.is_mock = ${useMock}
      AND ma.trade IN ('건축', '토목')
      AND pr.site_id = 'm15x-ph3-ibl'
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
  }>;

  // 시트1 — 출력인원: parser_reports.bp_summaries jsonb 펼침.
  const output_manpower: OutputManpowerRow[] = bp_summaries.map((s: any) => ({
    pjt: PJT,
    zone: String(s.zone ?? s.scope ?? "—"),
    trade: String(s.disc_abbrev ?? ""),
    bp_code: String(s.bp_code ?? s.company ?? ""),
    scope: String(s.scope ?? ""),
    main_work: String(s.work_text_today ?? ""),
    prev_work: String(s.work_text_yesterday ?? ""),
    today_work: String(s.work_text_today ?? ""),
    next_work: String(s.work_text_tomorrow ?? ""),
    early: 0,
    day: Number(s.today_incr_total ?? 0),
    overtime: 0,
  }));

  // 시트2 — 직종별 인원: parser_reports.job_allocations jsonb 펼침.
  const occupation_manpower: OccupationManpowerRow[] = job_allocations.map((j: any) => ({
    trade: String(j.disc_abbrev ?? ""),
    bp_code: String(j.bp_code ?? j.company ?? ""),
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
    bp_code: String(e.bp_code ?? e.company ?? ""),
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

  // 시트4 — 물량: parser_activities.
  const quantity: QuantityRow[] = acts.map((a) => ({
    zone: a.zone ?? "",
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
  return NextResponse.json(report);
}
