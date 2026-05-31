// 시연 데이터 초기화 — data/upload/ 하위 모든 batch 폴더 삭제.
// UserMenu 의 "시연 데이터 초기화" 버튼에서 호출됨 (NEXT_PUBLIC_DEMO_RESET=1 일 때만 노출).
//
// per-entry try/catch 로 부분 실패 허용. 한 폴더에서 권한 에러(EACCES)가 나도
// 나머지 폴더는 계속 시도 → failed[] 에 상세 reason 반환.
// 5535(uid 1001) 와 5537(uid 1000) 양쪽으로 업로드한 폴더가 섞여있을 때
// 한쪽에서 reset 을 누르면 자기 권한의 폴더만 정리되는 시나리오 대응.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

const DATA_DIR = path.join(process.cwd(), "..", "data");
const UPLOAD_DIR = path.join(DATA_DIR, "upload");

export async function DELETE() {
  const entries = await fs.readdir(UPLOAD_DIR, { withFileTypes: true }).catch(() => []);
  let deletedFolders = 0;
  let deletedFiles = 0;
  const failed: { path: string; error: string }[] = [];

  for (const entry of entries) {
    const full = path.join(UPLOAD_DIR, entry.name);
    try {
      if (entry.isDirectory()) {
        const inner = await fs.readdir(full).catch(() => []);
        await fs.rm(full, { recursive: true, force: true });
        deletedFiles += inner.length;
        deletedFolders += 1;
      } else if (entry.isFile()) {
        await fs.rm(full, { force: true });
        deletedFiles += 1;
      }
    } catch (e: any) {
      failed.push({
        path: entry.name,
        error: e?.code ? `${e.code}: ${e.message ?? "unknown"}` : (e?.message ?? "unknown"),
      });
    }
  }

  // failed 가 있어도 ok:true — 부분 성공도 정상 응답 (HTTP 200).
  // 클라이언트가 deletedFolders·deletedFiles·failed 를 보고 토스트 메시지 분기.
  return NextResponse.json({
    ok: true,
    deletedFolders,
    deletedFiles,
    failed,
  });
}
