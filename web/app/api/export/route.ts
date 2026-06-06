// GET /api/export?site_id=&date= — 통합작업일보 xlsx 출력을 FastAPI 로 프록시(BFF).
//
// 브라우저 export 버튼이 same-origin 으로 호출하면 서버(이 라우트)가 FASTAPI_URL
// (/export/run)로 중계한다. NEXT_PUBLIC_* 빌드타임 인라인·CORS·Cloudflare Tunnel
// (원격 브라우저의 localhost 불통) 문제를 한 번에 회피. xlsx 바이너리를 그대로
// 스트림하고 Content-Disposition(한글 파일명) 을 RFC5987 로 보존한다.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextRequest, NextResponse } from "next/server";

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const siteId = searchParams.get("site_id");
  const date = searchParams.get("date");
  if (!siteId || !date) {
    return NextResponse.json({ error: "site_id, date 필수" }, { status: 400 });
  }

  try {
    const upstream =
      `${FASTAPI_URL}/export/run` +
      `?site_id=${encodeURIComponent(siteId)}&date=${encodeURIComponent(date)}`;
    const res = await fetch(upstream, { signal: AbortSignal.timeout(120_000) });

    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      return NextResponse.json(
        { error: `FastAPI export 실패 (${res.status})`, detail },
        { status: 502 },
      );
    }

    const buf = await res.arrayBuffer();
    const filename = `통합작업일보_${date}.xlsx`;
    const headers = new Headers();
    headers.set(
      "Content-Type",
      res.headers.get("content-type") ??
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    );
    headers.set(
      "Content-Disposition",
      `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
    );
    return new NextResponse(buf, { status: 200, headers });
  } catch (e: any) {
    return NextResponse.json(
      { error: e?.message ?? "export 프록시 실패" },
      { status: 500 },
    );
  }
}
