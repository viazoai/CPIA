export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const data = await loadFixture("agent_tasks");
  const chat = await loadFixture("chat_sequence");
  return NextResponse.json({
    runs: data.daily_runs,
    progressByDate: data.progress_by_date,
    chatByDate: chat,
  });
}
