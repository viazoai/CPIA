// 시연 데이터 초기화 — 4 영역 정리:
//   1. data/upload/ 하위 batch 폴더 (uid 권한별 부분 실패 허용)
//   2. data/input/{DEMO_DATE}/ 의 파일 (파이프라인 collector 가 보는 위치)
//   3. pipeline_runs + run 이 적재하는 모든 sub-table (report_date = DEMO_DATE) —
//      cascade(daily_reports/forecasts/mapped_history/optimizer_advice) +
//      명시 삭제(parser_*/mapper_activities/agent_progress/mapping_corrections/
//      consolidated_reports/mapped_history_merge_log/prototype_l7_5_resolved/checkpoint*)
//   4. ChromaDB daily_activities — 해당 run_id 문서 삭제 (wbs_master 는 보존)
//
// UserMenu 의 "시연 데이터 초기화" 버튼에서 호출 (NEXT_PUBLIC_DEMO_RESET=1 게이트).
// per-entry try/catch — 한 영역 실패해도 나머지 진행.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";
import sql from "@/lib/pg";

const DATA_DIR = process.env.DATA_DIR ?? path.join(process.cwd(), "data");
const UPLOAD_DIR = path.join(DATA_DIR, "upload");
const INPUT_DIR = path.join(DATA_DIR, "input");

// 시연 date — 현재 데모 시나리오 "오늘". 다른 date 도 정리하려면 ?date= 로 override.
const DEFAULT_DEMO_DATE = "2025-09-25";

const CHROMA_BASE = `http://${process.env.CHROMA_HOST ?? "localhost"}:${process.env.CHROMA_PORT ?? "8000"}/api/v1`;

async function clearChromaForRunIds(runIds: string[]): Promise<{ deleted: number; error?: string }> {
  if (runIds.length === 0) return { deleted: 0 };
  try {
    // 컬렉션 ID 조회 (이름 → uuid)
    const listRes = await fetch(`${CHROMA_BASE}/collections`, { signal: AbortSignal.timeout(5000) });
    if (!listRes.ok) throw new Error(`chroma list failed: ${listRes.status}`);
    const collections = (await listRes.json()) as Array<{ id: string; name: string }>;
    const col = collections.find((c) => c.name === "daily_activities");
    if (!col) return { deleted: 0 }; // 컬렉션 없으면 패스

    // 삭제 전 대상 벡터 수 카운트 — v1 delete 응답이 null 일 수 있어(실측) 정확 보고용 사전 count.
    let preCount = 0;
    try {
      const getRes = await fetch(`${CHROMA_BASE}/collections/${col.id}/get`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ where: { run_id: { $in: runIds } }, include: [] }),
        signal: AbortSignal.timeout(10000),
      });
      if (getRes.ok) {
        const got = (await getRes.json().catch(() => null)) as { ids?: string[] } | null;
        preCount = Array.isArray(got?.ids) ? (got as { ids: string[] }).ids.length : 0;
      }
    } catch {
      /* count 실패해도 삭제는 진행 */
    }

    // run_id 기준 삭제 — wbs_master 는 건드리지 않음
    const delRes = await fetch(`${CHROMA_BASE}/collections/${col.id}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ where: { run_id: { $in: runIds } } }),
      signal: AbortSignal.timeout(10000),
    });
    if (!delRes.ok) throw new Error(`chroma delete failed: ${delRes.status}`);
    // v1 delete 응답은 삭제된 id 배열 또는 null — null 이면 (result.deleted 접근이 throw 나지 않게) 사전 count 사용.
    const result = (await delRes.json().catch(() => null)) as string[] | { deleted?: number } | null;
    const deleted = Array.isArray(result) ? result.length : (result?.deleted ?? preCount);
    return { deleted };
  } catch (e: any) {
    return { deleted: 0, error: e?.message ?? "chroma cleanup failed" };
  }
}

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
    // run 이 적재하는 모든 테이블을 run_id 기준으로 지운다. pipeline_runs FK delete_rule 별 처리:
    //   CASCADE   daily_reports/forecasts/mapped_history/optimizer_advice → pipeline_runs 삭제 시 자동
    //   NO ACTION consolidated_reports → 먼저 명시 삭제 필요
    //   SET NULL  mapping_corrections → cascade 안 됨, run_id=NULL 로 orphan 잔존 → 명시 삭제 필요
    //   FK 없음   parser_*/mapper_activities/agent_progress/mapped_history_merge_log/
    //             prototype_l7_5_resolved → 전부 명시 삭제 필요
    //   LangGraph checkpoints/checkpoint_blobs/checkpoint_writes → thread_id(=run_id, text) 기준 명시 삭제
    //   sites    row 자체는 보존하되 hours_saved_cum 은 삭제 run 기여분만큼 역산(RST-2), last_run_id 는 FK SET NULL
    //   (보존: activity_master·wbs_master·collector_inbox(Gmail dedup 원장, run-scoped 아님)·prototype_embedding_cache)
    //
    // Order: orphan / NO ACTION / SET NULL 먼저 → pipeline_runs 마지막 (cascade 나머지 처리).
    const runIds = (await (sql as any)`
      SELECT run_id FROM pipeline_runs WHERE report_date = ${date}
    `) as Array<{ run_id: string }>;
    if (runIds.length === 0) {
      return { deletedRuns: 0, deletedActivities: 0 };
    }
    const ids = runIds.map((r) => r.run_id);

    // sites.hours_saved_cum 역산 — reporter 가 run 완료 시 ((120-5)/60)*atomized_count 만큼 누적한 것을
    // (db.py:1133-1150) 삭제되는 run 들의 기여분만 빼서 되돌린다. reset→같은 데이터 재실행 시 KPI 중복가산 방지(RST-2).
    // pipeline_runs DELETE 전에 atomized_count 합산해야 함. sites row 자체는 보존(last_run_id 는 FK SET NULL).
    const siteDeltas = (await (sql as any)`
      SELECT site_id, COALESCE(SUM(atomized_count), 0)::float8 AS atom
      FROM pipeline_runs
      WHERE report_date = ${date} AND site_id IS NOT NULL
      GROUP BY site_id
    `) as Array<{ site_id: string; atom: number }>;
    for (const s of siteDeltas) {
      const deltaH = ((120 - 5) / 60) * Number(s.atom);
      if (deltaH > 0) {
        await (sql as any)`
          UPDATE sites SET hours_saved_cum = GREATEST(0, hours_saved_cum - ${deltaH}), updated_at = now()
          WHERE site_id = ${s.site_id}
        `;
      }
    }

    // orphan sub-tables (FK 없음)
    const parserA = await (sql as any)`DELETE FROM parser_activities WHERE run_id = ANY(${ids}::uuid[])`;
    const mapperA = await (sql as any)`DELETE FROM mapper_activities WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_reports WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_report_meta WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_worker_outputs WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_job_allocations WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM parser_equipment_allocations WHERE run_id = ANY(${ids}::uuid[])`;
    // 진행 게이지 / 머지로그 / l7_5 해석 캐시 (FK 없음)
    await (sql as any)`DELETE FROM agent_progress WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM mapped_history_merge_log WHERE run_id = ANY(${ids}::uuid[])`;
    await (sql as any)`DELETE FROM prototype_l7_5_resolved WHERE run_id = ANY(${ids}::uuid[])`;

    // SET NULL FK — cascade 안 되므로 명시 삭제
    await (sql as any)`DELETE FROM mapping_corrections WHERE run_id = ANY(${ids}::uuid[])`;

    // NO ACTION 테이블
    await (sql as any)`DELETE FROM consolidated_reports WHERE run_id = ANY(${ids}::uuid[])`;

    // LangGraph checkpoint 3종 — thread_id(text) = run_id 기준
    await (sql as any)`DELETE FROM checkpoint_writes WHERE thread_id = ANY(${ids}::text[])`;
    await (sql as any)`DELETE FROM checkpoint_blobs WHERE thread_id = ANY(${ids}::text[])`;
    await (sql as any)`DELETE FROM checkpoints WHERE thread_id = ANY(${ids}::text[])`;

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
  //    run_id 목록을 먼저 조회해 4번 ChromaDB 삭제에도 사용.
  const runIds = (await (sql as any)`
    SELECT run_id::text FROM pipeline_runs WHERE report_date = ${date}
  `).map((r: { run_id: string }) => r.run_id) as string[];

  const [db, chroma] = await Promise.all([
    clearDbForDate(date),
    clearChromaForRunIds(runIds),
  ]);

  return NextResponse.json({
    ok: true,
    deletedFolders: upload.folders,
    deletedFiles: upload.files + input.files,
    deletedRuns: db.deletedRuns,
    deletedActivities: db.deletedActivities,
    deletedVectors: chroma.deleted,
    failed: [...upload.failed, ...input.failed.map((f) => ({ ...f, path: `input/${date}/${f.path}` }))],
    dbError: db.error,
    chromaError: chroma.error,
    date,
  });
}
