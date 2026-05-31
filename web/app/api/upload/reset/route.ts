// 시연 데이터 초기화 — 3 영역 정리:
//   1. data/upload/ 하위 batch 폴더 (uid 권한별 부분 실패 허용)
//   2. data/input/{DEMO_DATE}/ 의 파일 (파이프라인 collector 가 보는 위치)
//   3. pipeline_runs + 관련 sub-tables (report_date = DEMO_DATE)
//
// UserMenu 의 "시연 데이터 초기화" 버튼에서 호출 (NEXT_PUBLIC_DEMO_RESET=1 게이트).
// per-entry try/catch — 한 영역 실패해도 나머지 진행.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";
import sql from "@/lib/pg";

const DATA_DIR = path.join(process.cwd(), "..", "data");
const UPLOAD_DIR = path.join(DATA_DIR, "upload");
const INPUT_DIR = path.join(DATA_DIR, "input");

// 시연 date — 현재 데모 시나리오 "오늘". 다른 date 도 정리하려면 ?date= 로 override.
const DEFAULT_DEMO_DATE = "2025-09-25";

async function clearDir(root: string): Promise<{ folders: number; files: number; failed: { path: string; error: string }[] }> {
  const entries = await fs.readdir(root, { withFileTypes: true }).catch(() => []);
  let folders = 0;
  let files = 0;
  const failed: { path: string; error: string }[] = [];
  for (const entry of entries) {
    const full = path.join(root, entry.name);
    try {
      if (entry.isDirectory()) {
        const inner = await fs.readdir(full).catch(() => []);
        await fs.rm(full, { recursive: true, force: true });
        files += inner.length;
        folders += 1;
      } else if (entry.isFile()) {
        await fs.rm(full, { force: true });
        files += 1;
      }
    } catch (e: any) {
      failed.push({
        path: entry.name,
        error: e?.code ? `${e.code}: ${e.message ?? "unknown"}` : (e?.message ?? "unknown"),
      });
    }
  }
  return { folders, files, failed };
}

async function clearDbForDate(date: string): Promise<{ deletedRuns: number; deletedActivities: number; error?: string }> {
  try {
    // FK on pipeline_runs:
    //   daily_reports/forecasts/mapped_history/optimizer_advice: CASCADE (자동 삭제됨)
    //   consolidated_reports: NO ACTION (먼저 명시 삭제 필요)
    //   parser_activities/mapper_activities/parser_*: FK 없음 (orphan — 명시 삭제 필요)
    //
    // Order: orphan / NO ACTION 먼저 → pipeline_runs 마지막 (cascade 나머지 처리).
    const runIds = (await (sql as any)`
      SELECT run_id FROM pipeline_runs WHERE report_date = ${date}
    `) as Array<{ run_id: string }>;
    if (runIds.length === 0) {
      return { deletedRuns: 0, deletedActivities: 0 };
    }
    const ids = runIds.map((r) => r.run_id);

    // orphan sub-tables (FK 없음)
    const parserA = await (sql as any)`DELETE FROM parser_activities WHERE run_id = ANY(${ids}::uuid[])`;
    const mapperA = await (sql as any)`DELETE FROM mapper_activities WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_reports WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_report_meta WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_worker_outputs WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_job_allocations WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_equipment_allocations WHERE run_id = ANY(${ids}::uuid[])`;

    // NO ACTION 테이블
    await (sql as any)`DELETE FROM consolidated_reports WHERE run_id = ANY(${ids}::uuid[])`;

    // main delete (cascade 가 daily_reports / forecasts / mapped_history / optimizer_advice 처리)
    const runs = await (sql as any)`DELETE FROM pipeline_runs WHERE report_date = ${date}`;

    return {
      deletedRuns: runs?.count ?? ids.length,
      deletedActivities: (parserA?.count ?? 0) + (mapperA?.count ?? 0),
    };
  } catch (e: any) {
    return { deletedRuns: 0, deletedActivities: 0, error: e?.message ?? "db cleanup failed" };
  }
}

export async function DELETE(req: Request) {
  const url = new URL(req.url);
  const date = url.searchParams.get("date") ?? DEFAULT_DEMO_DATE;

  // 1. data/upload/ (다중 batch 폴더)
  const upload = await clearDir(UPLOAD_DIR);

  // 2. data/input/{date}/ (파이프라인 collector input)
  const inputDir = path.join(INPUT_DIR, date.replace(/-/g, ""));
  const input = await clearDir(inputDir);

  // 3. DB (해당 date 의 pipeline_runs + 관련 sub-tables)
  const db = await clearDbForDate(date);

  return NextResponse.json({
    ok: true,
    deletedFolders: upload.folders,
    deletedFiles: upload.files + input.files,
    deletedRuns: db.deletedRuns,
    deletedActivities: db.deletedActivities,
    failed: [...upload.failed, ...input.failed.map((f) => ({ ...f, path: `input/${date}/${f.path}` }))],
    dbError: db.error,
    date,
  });
}
