// GET /api/runs/items?run_id=X&agent=Mapper
//
// 단계별 실제 아이템을 단계 고유 스키마(AgentTaskRow)로 반환.
// 컬럼 정의는 lib/agent-task-schema.ts (AGENT_COLUMNS) 단일 source.
//   Collector   — data/input/YYYYMMDD/ 파일 (공종·업체·파일명)
//   Parser      — 업체 × 시트카테고리(작업내용1/인원2/장비3/물량4) 처리건수
//   Mapper      — mapper_activities (공종·업체·작업내용·WBS)
//   Human Review — requires_review=true (+ 확신도)
//   Atomizer    — mapper_activities (작업내용=시트1, 작업사항=시트4)
//   Exporter    — daily_reports 통합 1건
//   Forecaster  — wp_summary_jsonb (WP grain: wa·l6·company) — Work Area 분리
//   Optimizer   — wp_summary ∩ optimizer_advice (+ 단축가능일=recovery_days)
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentTaskRow, AgentItemTone } from "@/lib/types";

const DATA_DIR = path.join(process.cwd(), "..", "data");

const TONE_SORT: Record<AgentItemTone, number> = {
  processing: 0, received: 1, hil_pending: 2, blocked: 3,
  risk: 4, caution: 5, done: 6, normal: 7,
};

function sortRows(rows: AgentTaskRow[]): AgentTaskRow[] {
  return [...rows].sort((a, b) => (TONE_SORT[a.statusTone] ?? 9) - (TONE_SORT[b.statusTone] ?? 9));
}

// "cub-철근콘크리트공사-남웅건설" → "CUB" / "fab-..." → "FAB" / "unknown-..." → "—"
function waFromWpId(wpId: string): string {
  const seg = (wpId || "").split("-")[0]?.toUpperCase() ?? "";
  return seg && seg !== "UNKNOWN" ? seg : "—";
}

function fmtDelay(d: number | null | undefined): string {
  if (d == null) return "—";
  const n = Math.round(d);
  return n > 0 ? `+${n}일` : `${n}일`;
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const runId = url.searchParams.get("run_id");
  const agent = url.searchParams.get("agent");

  if (!runId || !agent) {
    return NextResponse.json({ ok: false, error: "run_id, agent 파라미터 필요" }, { status: 400 });
  }

  try {
    let rows: AgentTaskRow[] = [];

    if (agent === "Collector") {
      const runRows = (await (sql as any)`
        SELECT TO_CHAR(report_date, 'YYYYMMDD') AS date_compact
        FROM pipeline_runs WHERE run_id = ${runId} LIMIT 1
      `) as Array<{ date_compact: string }>;
      const dateCompact = runRows[0]?.date_compact ?? "";

      // 업체 → 공종(건축/토목) 대표값. parser_activities.trade 에 건축/토목이 들어감(l5_disc 는 빈값).
      const tradeRows = (await (sql as any)`
        SELECT company, MAX(trade) AS trade
        FROM parser_activities WHERE run_id = ${runId} GROUP BY company
      `) as Array<{ company: string; trade: string | null }>;
      const tradeByCompany = new Map(tradeRows.map((r) => [r.company, r.trade ?? "—"]));
      const companies = tradeRows.map((r) => r.company);

      // 1) 디스크 파일 우선 (당일/라이브 run — data/input/YYYYMMDD)
      if (dateCompact) {
        const inputDir = path.join(DATA_DIR, "input", dateCompact);
        const all = await fs.readdir(inputDir).catch(() => [] as string[]);
        const files = all.filter((f) => /\.(xlsx|xlsm)$/i.test(f));
        rows = files.map((f, i) => {
          const isIntegrated = /통합/.test(f);
          const matched = companies.find((c) => c && f.includes(c));
          const company = isIntegrated ? "(통합)" : matched ?? f.split("_")[0];
          const trade = isIntegrated ? "전체" : tradeByCompany.get(matched ?? "") ?? "—";
          return {
            id: String(i + 1).padStart(3, "0"),
            values: { trade, company, file: f },
            statusLabel: "수집완료",
            statusTone: "done" as AgentItemTone,
          };
        });
      }
      // 2) 디스크에 없으면(과거 run — 파일 미보관) 업체 목록으로 대체
      if (rows.length === 0) {
        rows = tradeRows.map((r, i) => ({
          id: String(i + 1).padStart(3, "0"),
          values: { trade: r.trade ?? "—", company: r.company, file: `${r.company} 작업일보` },
          statusLabel: "수집완료",
          statusTone: "done" as AgentItemTone,
        }));
      }
    }

    else if (agent === "Parser") {
      // 업체 × 시트카테고리 처리건수
      const [qty, job, equip, content] = (await Promise.all([
        (sql as any)`SELECT company, COUNT(*)::int AS c, MAX(trade) AS trade
                     FROM parser_activities WHERE run_id = ${runId} GROUP BY company`,
        (sql as any)`SELECT company, COUNT(*)::int AS c
                     FROM parser_job_allocations WHERE run_id = ${runId} GROUP BY company`,
        (sql as any)`SELECT company, COUNT(*)::int AS c
                     FROM parser_equipment_allocations WHERE run_id = ${runId} GROUP BY company`,
        (sql as any)`SELECT e->>'company' AS company, COUNT(*)::int AS c
                     FROM parser_reports pr, jsonb_array_elements(pr.bp_summaries) e
                     WHERE pr.run_id = ${runId} GROUP BY 1`,
      ])) as Array<Array<{ company: string; c: number; trade?: string | null }>>;

      const tradeBy = new Map(qty.map((r) => [r.company, r.trade ?? "—"]));
      const cnt = (arr: Array<{ company: string; c: number }>, co: string) =>
        arr.find((r) => r.company === co)?.c ?? 0;
      const companies = Array.from(
        new Set([...qty, ...job, ...equip, ...content].map((r) => r.company).filter(Boolean)),
      );
      const CATS: Array<[string, (co: string) => number]> = [
        ["작업내용 (시트1)", (co) => cnt(content, co)],
        ["인원 (시트2)", (co) => cnt(job, co)],
        ["장비 (시트3)", (co) => cnt(equip, co)],
        ["물량 (시트4)", (co) => cnt(qty, co)],
      ];
      rows = companies.flatMap((co) =>
        CATS.map(([label, getc], i) => ({
          id: `${co}-${i}`,
          values: { trade: tradeBy.get(co) ?? "—", company: co, category: label, count: String(getc(co)) },
          statusLabel: "파싱완료",
          statusTone: "done" as AgentItemTone,
        })),
      );
    }

    else if (agent === "Mapper") {
      const r = (await (sql as any)`
        SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) AS trade, ma.company,
               pa.work_content, ma.l6_main
        FROM mapper_activities ma
        LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
        WHERE ma.run_id = ${runId} ORDER BY ma.idx
      `) as Array<{ idx: number; trade: string | null; company: string; work_content: string | null; l6_main: string | null }>;
      rows = r.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: {
          trade: a.trade ?? "—",
          company: a.company,
          work: a.work_content ?? "—",
          wbs: a.l6_main ?? "(미매핑)",
        },
        statusLabel: a.l6_main != null ? "매핑완료" : "검토필요",
        statusTone: (a.l6_main != null ? "done" : "hil_pending") as AgentItemTone,
      }));
    }

    else if (agent === "Human Review") {
      const r = (await (sql as any)`
        SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) AS trade, ma.company,
               pa.work_content, ma.l6_main, ma.mapping_conf, ma.requires_review
        FROM mapper_activities ma
        LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
        WHERE ma.run_id = ${runId}
        ORDER BY ma.requires_review DESC, ma.mapping_conf ASC NULLS FIRST, ma.idx
      `) as Array<{ idx: number; trade: string | null; company: string; work_content: string | null; l6_main: string | null; mapping_conf: number | null; requires_review: boolean }>;
      rows = r.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: {
          trade: a.trade ?? "—",
          company: a.company,
          work: a.work_content ?? "—",
          wbs: a.l6_main ?? "(대안 검토)",
          conf: a.mapping_conf != null ? `${Math.round(Number(a.mapping_conf) * 100)}%` : "—",
        },
        statusLabel: a.requires_review ? "검토대기" : "검토완료",
        statusTone: (a.requires_review ? "hil_pending" : "done") as AgentItemTone,
      }));
    }

    else if (agent === "Atomizer") {
      // 작업내용=시트1(parser_reports.bp_summaries.work_text_today, 업체별), 작업사항=시트4(parser_activities.work_content)
      const [acts, s1] = (await Promise.all([
        (sql as any)`SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) AS trade, ma.company, pa.work_content
                     FROM mapper_activities ma
                     LEFT JOIN parser_activities pa ON pa.run_id = ma.run_id AND pa.idx = ma.idx
                     WHERE ma.run_id = ${runId} ORDER BY ma.idx`,
        (sql as any)`SELECT e->>'company' AS company, e->>'work_text_today' AS wt
                     FROM parser_reports pr, jsonb_array_elements(pr.bp_summaries) e
                     WHERE pr.run_id = ${runId} AND e->>'work_text_today' IS NOT NULL`,
      ])) as [
        Array<{ idx: number; trade: string | null; company: string; work_content: string | null }>,
        Array<{ company: string; wt: string | null }>,
      ];
      const s1By = new Map<string, string>();
      for (const r of s1) if (r.company && !s1By.has(r.company)) s1By.set(r.company, r.wt ?? "");
      rows = acts.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: {
          trade: a.trade ?? "—",
          company: a.company,
          work: s1By.get(a.company) || "—",
          activity: a.work_content ?? "—",
        },
        statusLabel: "적재완료",
        statusTone: "done" as AgentItemTone,
      }));
    }

    else if (agent === "Exporter") {
      const r = (await (sql as any)`
        SELECT report_date, COALESCE(jsonb_array_length(
                 (SELECT wp_summary_jsonb FROM daily_reports d2 WHERE d2.run_id = ${runId}
                   AND wp_summary_jsonb IS NOT NULL ORDER BY created_at DESC LIMIT 1)), 0) AS act_cnt
        FROM pipeline_runs WHERE run_id = ${runId} LIMIT 1
      `) as Array<{ report_date: Date | string; act_cnt: number }>;
      const meta = r[0];
      if (meta) {
        const dStr = typeof meta.report_date === "string"
          ? meta.report_date.slice(0, 10)
          : meta.report_date.toISOString().slice(0, 10);
        rows = [{
          id: "001",
          values: { date: dStr, report: "통합 작업일보", count: String(meta.act_cnt ?? 0) },
          statusLabel: "생성완료",
          statusTone: "done" as AgentItemTone,
        }];
      }
    }

    else if (agent === "Forecaster" || agent === "Optimizer") {
      // report 경로 WP grain (wa, l6, company) — wp_summary_jsonb
      const wpRows = (await (sql as any)`
        SELECT wp_summary_jsonb AS wp FROM daily_reports
        WHERE run_id = ${runId} AND wp_summary_jsonb IS NOT NULL
        ORDER BY created_at DESC LIMIT 1
      `) as Array<{ wp: any[] }>;
      const wps: any[] = wpRows[0]?.wp ?? [];

      // 지연일: forecasts (company, l6) MAX(delay_days) — forecasts엔 wa 없음
      const fRows = (await (sql as any)`
        SELECT company, l6_main, MAX(delay_days)::float AS delay
        FROM forecasts WHERE run_id = ${runId} GROUP BY company, l6_main
      `) as Array<{ company: string; l6_main: string; delay: number | null }>;
      const delayBy = new Map(fRows.map((r) => [`${r.company}|${r.l6_main}`, r.delay]));

      if (agent === "Forecaster") {
        rows = wps.map((w, i) => ({
          id: String(w.wp_id ?? i),
          values: {
            warea: waFromWpId(w.wp_id ?? ""),
            wbs: w.trade ?? "—",
            company: w.bp_name ?? "—",
            delay: fmtDelay(delayBy.get(`${w.bp_name}|${w.trade}`)),
            diag: w.risk_level ?? "—",
          },
          statusLabel: "완료",
          statusTone: "done" as AgentItemTone,
        }));
      } else {
        // Optimizer — 조언 대상(optimizer_advice) WP 만, + 단축가능일=recovery_days
        const oRows = (await (sql as any)`
          SELECT DISTINCT company, l6_main FROM optimizer_advice WHERE run_id = ${runId}
        `) as Array<{ company: string; l6_main: string }>;
        const advised = new Set(oRows.map((r) => `${r.company}|${r.l6_main}`));
        rows = wps
          .filter((w) => advised.has(`${w.bp_name}|${w.trade}`))
          .map((w, i) => ({
            id: String(w.wp_id ?? i),
            values: {
              warea: waFromWpId(w.wp_id ?? ""),
              wbs: w.trade ?? "—",
              company: w.bp_name ?? "—",
              delay: fmtDelay(delayBy.get(`${w.bp_name}|${w.trade}`)),
              recover: w.recovery_days != null ? `-${Math.round(Number(w.recovery_days))}일` : "—",
              diag: w.risk_level ?? "—",
            },
            statusLabel: "완료",
            statusTone: "done" as AgentItemTone,
          }));
      }
    }

    return NextResponse.json({ ok: true, items: sortRows(rows) });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message ?? "query failed" },
      { status: 500 },
    );
  }
}
