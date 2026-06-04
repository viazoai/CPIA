// 통합 작업일보 시트1(출력인원/작업사항) 행 빌더 — route.ts 에서 호출하는 순수 함수.
// 9/25 실업로드는 parser_reports.bp_summaries, 시드일은 mapper_activities 집계에서 재구성.
import type { OutputManpowerRow } from "@/lib/types";

const PJT = "M15X Ph-3 IBL";

/** "BP사" 컬럼 값 = 업체명 우선, 코드 폴백 (spec D5). 빈문자/0 은 폴백. */
export function bpLabel(company: unknown, bpCode: unknown): string {
  const c = company == null ? "" : String(company);
  if (c !== "") return c;
  return bpCode == null ? "" : String(bpCode);
}

/**
 * 9/25 실업로드: parser_reports.bp_summaries jsonb 원소 → 시트1 행(원소 1개 = 업체 1개).
 * prevWork: D-1 날짜의 업체별 금일 작업텍스트 맵, nextWork: D+1 날짜의 업체별 금일 작업텍스트 맵.
 * 두 맵은 route 레이어에서 계산해 전달한다.
 */
export function outputFromBpSummaries(
  bpSummaries: any[],
  companyWa: Record<string, string>,
  prevWork: Record<string, string> = {},
  nextWork: Record<string, string> = {},
): OutputManpowerRow[] {
  return bpSummaries.map((s) => ({
    pjt: PJT,
    zone: String(companyWa[s.company] ?? s.zone ?? ""),
    trade: String(s.disc_abbrev ?? ""),
    bp_code: bpLabel(s.company, s.bp_code), // D5: 업체명
    scope: String(s.scope ?? ""),
    main_work: String(s.work_text_today ?? ""),
    prev_work: String(prevWork[s.company] ?? ""),  // D-1 날짜의 해당 업체 금일 작업
    today_work: String(s.work_text_today ?? ""),
    next_work: String(nextWork[s.company] ?? ""),  // D+1 날짜의 해당 업체 금일 작업
    early: 0,
    day: Number(s.today_incr_total ?? 0),
    overtime: 0,
  }));
}

/** 시드일 mapper per-company 집계 행 (route 의 새 쿼리 결과). */
export interface MapperOutputAgg {
  company: string;
  trade: string | null;
  workers_total: number;
  work_today: string | null;
}

/**
 * 시드일: mapper 집계 → 시트1 행(per-company).
 * prevWork: D-1 날짜의 업체별 금일 작업텍스트 맵, nextWork: D+1 날짜의 업체별 금일 작업텍스트 맵.
 * 두 맵은 route 레이어에서 계산해 전달한다.
 */
export function reconstructOutputFromMapper(
  aggRows: MapperOutputAgg[],
  companyWa: Record<string, string>,
  prevWork: Record<string, string> = {},
  nextWork: Record<string, string> = {},
): OutputManpowerRow[] {
  return aggRows.map((r) => ({
    pjt: PJT,
    zone: String(companyWa[r.company] ?? ""),
    trade: String(r.trade ?? ""),
    bp_code: bpLabel(r.company, null), // 시드 bp_code 빈값 → 업체명
    scope: "",
    main_work: String(r.work_today ?? ""),
    prev_work: String(prevWork[r.company] ?? ""),  // D-1 날짜의 해당 업체 금일 작업
    today_work: String(r.work_today ?? ""),
    next_work: String(nextWork[r.company] ?? ""),  // D+1 날짜의 해당 업체 금일 작업
    early: 0,
    day: Math.round(r.workers_total ?? 0),
    overtime: 0,
  }));
}
