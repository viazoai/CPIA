import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const data = await loadFixture("report");
  return NextResponse.json(data);
}
