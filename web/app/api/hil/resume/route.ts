// POST /api/hil/resume — HIL 1 승인 신호를 FastAPI resume 엔드포인트로 프록시.
//
// review 화면의 "확정" 액션이 호출한다. body.run_id 가 없으면 현재
// waiting_hil_1 상태인 최신 run 을 자동 선택(단일 PoC). corrections 가 비어도
// (= 모두 AI 추천 수용) FastAPI 가 truthy 래퍼로 감싸 resume 하므로 정상 진행.
//
// FastAPI resume 은 동기로 graph 를 재개하므로, 다운스트림이 길면 오래 걸릴 수
// 있다. FE 는 이 호출을 fire-and-forget 으로 보내고 tasks 화면 polling 으로
// 진행을 관전한다. 여기서는 넉넉한 timeout 만 둔다.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextRequest, NextResponse } from "next/server";
import sql from "@/lib/pg";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json().catch(() => ({}))) as {
      run_id?: string;
      corrections?: Record<string, { wa: string; l6_main: string }>;
    };
    const corrections = body?.corrections ?? {};

    let runId = body?.run_id;
    if (!runId) {
      const rows = (await (sql as any)`
        SELECT run_id FROM pipeline_runs
        WHERE status = 'waiting_hil_1'
        ORDER BY started_at DESC
        LIMIT 1
      `) as Array<{ run_id: string }>;
      runId = rows[0]?.run_id;
    }
    if (!runId) {
      return NextResponse.json(
        { ok: false, error: "검토 대기(waiting_hil_1) 중인 run 이 없습니다." },
        { status: 404 },
      );
    }

    const res = await fetch(`${FASTAPI_URL}/api/runs/${runId}/hil_1/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ corrections }),
      signal: AbortSignal.timeout(170_000),
    });
    const data = (await res.json().catch(() => ({}))) as { next_node?: string; detail?: unknown };
    if (!res.ok) {
      return NextResponse.json(
        { ok: false, run_id: runId, status: res.status, detail: data?.detail ?? data },
        { status: 502 },
      );
    }
    return NextResponse.json({ ok: true, run_id: runId, next_node: data?.next_node ?? null });
  } catch (e: any) {
    return NextResponse.json({ ok: false, error: e?.message ?? "resume 실패" }, { status: 500 });
  }
}
