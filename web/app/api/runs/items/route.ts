// GET /api/runs/items?run_id=X&agent=Y
//
// 각 파이프라인 단계의 실제 DB 테이블을 직독해 { ok, agent, columns, items } 반환.
// columns 는 단계마다 다르므로 API 가 함께 반환 (FE 가 props 로 수신).
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import sql from "@/lib/pg";
import type { AgentColumn, AgentTaskRow } from "@/lib/types";
import { AGENT_COLUMNS, PARSER_COLUMNS_FULL, PARSER_COLUMNS_AGG } from "@/lib/agent-task-schema";
import { recoveryRepDays, toneFromRisk, parserMode, condText, sortRows } from "@/lib/agent-task-rows";

const DATA_DIR = process.env.DATA_DIR ?? path.join(process.cwd(), "data");

function fmtDelay(d: number | null | undefined): string {
  if (d == null) return "—";
  const n = Math.round(Number(d));
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
    let columns: AgentColumn[] = AGENT_COLUMNS[agent] ?? [];

    if (agent === "Collector") {
      const runRows = (await (sql as any)`
        SELECT TO_CHAR(report_date,'YYYYMMDD') AS d FROM pipeline_runs WHERE run_id=${runId} LIMIT 1`) as Array<{ d: string }>;
      const dateCompact = runRows[0]?.d ?? "";
      const tradeRows = (await (sql as any)`
        SELECT company, MAX(trade) AS trade FROM parser_activities WHERE run_id=${runId} GROUP BY company`) as Array<{ company: string; trade: string | null }>;
      // 디스크 파일 우선, 없으면 업체목록 폴백
      let files: string[] = [];
      if (dateCompact) {
        const all = await fs.readdir(path.join(DATA_DIR, "input", dateCompact)).catch(() => [] as string[]);
        files = all.filter((f) => /\.(xlsx|xlsm)$/i.test(f));
      }
      if (files.length > 0) {
        rows = files.map((f, i) => {
          const matched = tradeRows.find((r) => r.company && f.includes(r.company));
          return {
            id: String(i + 1).padStart(3, "0"),
            values: { trade: matched?.trade ?? (/통합/.test(f) ? "전체" : "—"), company: matched?.company ?? f.split("_")[0], file: f },
            statusLabel: "수집완료", statusTone: "done",
          };
        });
      } else {
        rows = tradeRows.map((r, i) => ({
          id: String(i + 1).padStart(3, "0"),
          values: { trade: r.trade ?? "—", company: r.company, file: `${r.company} 작업일보` },
          statusLabel: "수집완료", statusTone: "done",
        }));
      }
    }

    else if (agent === "Parser") {
      const [qty, job, equip, content] = (await Promise.all([
        (sql as any)`SELECT company, COUNT(*)::int c, MAX(trade) trade FROM parser_activities WHERE run_id=${runId} GROUP BY company`,
        (sql as any)`SELECT company, COUNT(*)::int c FROM parser_job_allocations WHERE run_id=${runId} GROUP BY company`,
        (sql as any)`SELECT company, COUNT(*)::int c FROM parser_equipment_allocations WHERE run_id=${runId} GROUP BY company`,
        (sql as any)`SELECT e->>'company' company, COUNT(*)::int c FROM parser_reports pr, jsonb_array_elements(pr.bp_summaries) e WHERE pr.run_id=${runId} GROUP BY 1`,
      ])) as Array<Array<{ company: string; c: number; trade?: string | null }>>;
      const totals = {
        content: content.reduce((s, r) => s + r.c, 0),
        job: job.reduce((s, r) => s + r.c, 0),
        equip: equip.reduce((s, r) => s + r.c, 0),
      };
      const tradeBy = new Map(qty.map((r) => [r.company, r.trade ?? "—"]));
      if (parserMode(totals) === "agg") {
        columns = PARSER_COLUMNS_AGG;
        rows = qty.map((r, i) => ({
          id: String(i + 1).padStart(3, "0"),
          values: { trade: r.trade ?? "—", company: r.company, count: String(r.c) },
          statusLabel: "파싱완료", statusTone: "done",
        }));
      } else {
        columns = PARSER_COLUMNS_FULL;
        const cnt = (arr: Array<{ company: string; c: number }>, co: string) => arr.find((r) => r.company === co)?.c ?? 0;
        const companies = Array.from(new Set([...qty, ...job, ...equip, ...content].map((r) => r.company).filter(Boolean)));
        const CATS: Array<[string, (co: string) => number]> = [
          ["작업내용", (co) => cnt(content, co)],
          ["인원", (co) => cnt(job, co)],
          ["장비", (co) => cnt(equip, co)],
          ["물량", (co) => cnt(qty, co)],
        ];
        rows = companies.flatMap((co) =>
          CATS.map(([label, getc], i) => ({
            id: `${co}-${i}`,
            values: { trade: tradeBy.get(co) ?? "—", company: co, category: label, count: String(getc(co)) },
            statusLabel: "파싱완료", statusTone: "done" as const,
          })),
        );
      }
    }

    else if (agent === "Mapper") {
      const r = (await (sql as any)`
        SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, pa.work_content, ma.l6_main
        FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
        WHERE ma.run_id=${runId} ORDER BY ma.idx`) as Array<any>;
      rows = r.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: { trade: a.trade ?? "—", company: a.company, work: a.work_content ?? "—", wbs: a.l6_main ?? "(미매핑)" },
        statusLabel: a.l6_main != null ? "매핑완료" : "검토필요",
        statusTone: a.l6_main != null ? "done" : "hil_pending",
      }));
    }

    else if (agent === "Human Review") {
      const r = (await (sql as any)`
        SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, pa.work_content, ma.l6_main, ma.mapping_conf, ma.requires_review
        FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
        WHERE ma.run_id=${runId} ORDER BY ma.requires_review DESC, ma.mapping_conf ASC NULLS FIRST, ma.idx`) as Array<any>;
      rows = r.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: {
          trade: a.trade ?? "—", company: a.company, work: a.work_content ?? "—",
          wbs: a.l6_main ?? "(대안 검토)",
          conf: a.mapping_conf != null ? `${Math.round(Number(a.mapping_conf) * 100)}%` : "—",
        },
        statusLabel: a.requires_review ? "검토대기" : "검토완료",
        statusTone: a.requires_review ? "hil_pending" : "done",
      }));
    }

    else if (agent === "Atomizer") {
      const r = (await (sql as any)`
        SELECT ma.idx, COALESCE(ma.l5_disc, ma.trade) trade, ma.company, ma.l6_main, ma.conditions, pa.work_content
        FROM mapper_activities ma LEFT JOIN parser_activities pa ON pa.run_id=ma.run_id AND pa.idx=ma.idx
        WHERE ma.run_id=${runId} AND ma.l6_main IS NOT NULL ORDER BY ma.idx`) as Array<any>;
      rows = r.map((a) => ({
        id: String(a.idx).padStart(3, "0"),
        values: {
          trade: a.trade ?? "—", company: a.company, wbs: a.l6_main ?? "—",
          work: a.work_content ?? "—",
          cond: condText(typeof a.conditions === "string" ? JSON.parse(a.conditions) : a.conditions),
        },
        statusLabel: "적재완료", statusTone: "done",
      }));
    }

    else if (agent === "Exporter") {
      const r = (await (sql as any)`
        SELECT TO_CHAR(report_date,'YYYY-MM-DD') d, COALESCE(atomized_count,0) cnt
        FROM pipeline_runs WHERE run_id=${runId} LIMIT 1`) as Array<{ d: string; cnt: number }>;
      if (r[0]) rows = [{ id: "001", values: { date: r[0].d, report: "통합 작업일보", count: String(r[0].cnt) }, statusLabel: "생성완료", statusTone: "done" }];
    }

    else if (agent === "Forecaster") {
      const r = (await (sql as any)`
        SELECT wa, l6_main, company, delay_days, risk_level FROM forecasts WHERE run_id=${runId}
        ORDER BY (risk_level='이상') DESC, (risk_level='주의') DESC, delay_days DESC NULLS LAST`) as Array<any>;
      rows = r.map((f, i) => ({
        id: String(i + 1).padStart(3, "0"),
        values: { warea: f.wa ?? "—", wbs: f.l6_main ?? "—", company: f.company ?? "—", delay: fmtDelay(f.delay_days) },
        statusLabel: f.risk_level ?? "—", statusTone: toneFromRisk(f.risk_level),
      }));
    }

    else if (agent === "Optimizer") {
      // optimizer_advice 에 wa 가 없고 (company,l6_main) 이 FAB/CUB 로 중복될 수 있어
      // forecasts JOIN 이 다대다 fan-out 한다. advice 1행당 1결과로 묶되(최고위험 forecast 채택),
      // optimizer_advice 실 행수와 카드 건수를 일치시킨다.
      const r = (await (sql as any)`
        SELECT DISTINCT ON (oa.id) oa.company, oa.l6_main, oa.recovery_distribution, f.wa, f.delay_days, f.risk_level
        FROM optimizer_advice oa
        LEFT JOIN forecasts f ON f.run_id=oa.run_id AND f.company=oa.company AND f.l6_main=oa.l6_main
        WHERE oa.run_id=${runId}
        ORDER BY oa.id, (f.risk_level='이상') DESC, (f.risk_level='주의') DESC, f.delay_days DESC NULLS LAST`) as Array<any>;
      rows = r.map((o, i) => ({
        id: String(i + 1).padStart(3, "0"),
        values: {
          warea: o.wa ?? "—", wbs: o.l6_main ?? "—", company: o.company ?? "—",
          delay: fmtDelay(o.delay_days),
          recover: recoveryRepDays(typeof o.recovery_distribution === "string" ? JSON.parse(o.recovery_distribution) : o.recovery_distribution),
        },
        statusLabel: o.risk_level ?? "—", statusTone: toneFromRisk(o.risk_level),
      }));
    }

    return NextResponse.json({ ok: true, agent, columns, items: sortRows(rows) });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message ?? "query failed" },
      { status: 500 },
    );
  }
}
