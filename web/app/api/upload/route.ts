// 작업일보 업로드 — multipart/form-data 로 다중 파일 수신.
// 저장 경로 2곳 (시연 + 파이프라인 양측 모두 보임):
//   1. data/upload/YYYYMMDD-HHmmss/<filename>     ← 업로드 audit log 용 batch 폴더
//   2. data/input/<simDate>/<filename>            ← pipeline collector 가 보는 위치
//        simDate = 파일명 첫 매칭 _YYYYMMDD 패턴 (예: _20250925.xlsx → 20250925)
//        없으면 today 시스템 날짜 fallback
// fixtures.ts 와 동일 컨벤션: path.join(process.cwd(), "..", "data")
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextRequest, NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "..", "data");
const UPLOAD_DIR = path.join(DATA_DIR, "upload");
const INPUT_DIR = path.join(DATA_DIR, "input");
const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";

async function triggerPipeline(simDate: string, siteId = "m15x-ph3-ibl"): Promise<string | null> {
  try {
    const res = await fetch(`${FASTAPI_URL}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ site_id: siteId, report_date: simDate }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { run_id?: string };
    return data.run_id ?? null;
  } catch {
    return null;
  }
}

function tsFolder(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function todayCompact(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

function safeName(name: string): string {
  // 경로 탈출 방지 + 공백/한글 보존.
  const base = path.basename(name);
  return base.replace(/[/\\:*?"<>|]/g, "_");
}

function parseSimDate(names: string[]): string {
  // 파일명에서 _YYYYMMDD 패턴 추출 (확장자 직전).
  for (const n of names) {
    const m = n.match(/_(\d{8})\.[a-z]+$/i);
    if (m) return m[1];
  }
  return todayCompact();
}

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    const files = form.getAll("files").filter((f): f is File => f instanceof File);

    if (files.length === 0) {
      return NextResponse.json({ ok: false, error: "no files" }, { status: 400 });
    }

    const batchDir = path.join(UPLOAD_DIR, tsFolder());
    await fs.mkdir(batchDir, { recursive: true });

    // simDate = 파일명 기반 YYYYMMDD (pipeline 의 data/input/YYYYMMDD/ 와 매칭).
    const simDate = parseSimDate(files.map((f) => f.name));
    const inputDir = path.join(INPUT_DIR, simDate);
    await fs.mkdir(inputDir, { recursive: true });

    const saved: { name: string; size: number }[] = [];
    for (const file of files) {
      const buf = Buffer.from(await file.arrayBuffer());
      const name = safeName(file.name);
      // 1. upload audit log
      await fs.writeFile(path.join(batchDir, name), buf);
      // 2. pipeline input (덮어쓰기 OK — 같은 파일명이면 최신 업로드가 처리됨)
      await fs.writeFile(path.join(inputDir, name), buf);
      saved.push({ name, size: buf.length });
    }

    // FastAPI /run 호출 — 성공하면 run_id 반환, 실패해도 업로드 자체는 성공.
    const runId = await triggerPipeline(simDate);

    return NextResponse.json({
      ok: true,
      count: saved.length,
      folder: path.relative(DATA_DIR, batchDir),
      inputDir: path.relative(DATA_DIR, inputDir),
      simDate,
      files: saved,
      run_id: runId,       // null 이면 FastAPI 미연결 (sim fallback)
    });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message ?? "upload failed" },
      { status: 500 },
    );
  }
}
