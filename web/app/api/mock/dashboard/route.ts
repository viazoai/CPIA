import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const sites = await loadFixture("sites");
  const dashboard = await loadFixture("dashboard");
  return NextResponse.json({ sites, dashboard });
}
