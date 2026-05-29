// 작업일보 업로드 — multipart/form-data 로 다중 파일 수신.
// 저장 경로: data/upload/YYYYMMDD-HHmmss/<filename>
// fixtures.ts 와 동일 컨벤션: path.join(process.cwd(), "..", "data")
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextRequest, NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "..", "data");
const UPLOAD_DIR = path.join(DATA_DIR, "upload");

function tsFolder(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

function safeName(name: string): string {
  // 경로 탈출 방지 + 공백/한글 보존.
  const base = path.basename(name);
  return base.replace(/[/\\:*?"<>|]/g, "_");
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

    const saved: { name: string; size: number }[] = [];
    for (const file of files) {
      const buf = Buffer.from(await file.arrayBuffer());
      const name = safeName(file.name);
      await fs.writeFile(path.join(batchDir, name), buf);
      saved.push({ name, size: buf.length });
    }

    return NextResponse.json({
      ok: true,
      count: saved.length,
      folder: path.relative(DATA_DIR, batchDir),
      files: saved,
    });
  } catch (e: any) {
    return NextResponse.json(
      { ok: false, error: e?.message ?? "upload failed" },
      { status: 500 },
    );
  }
}
