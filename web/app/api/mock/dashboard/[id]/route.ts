import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const sites = await loadFixture("sites");
  const dashboard = await loadFixture("dashboard");
  const report = await loadFixture("report");

  const site = sites.find((s) => s.id === params.id);
  if (!site) return NextResponse.json({ error: "not found" }, { status: 404 });

  const latestDate = report.daily[0]?.date;
  const detail = latestDate ? report.details[latestDate] : null;

  const perSiteAutomation = dashboard.impact.per_site_automation[params.id] || dashboard.impact.per_site_automation["m15x-ph3-ibl"] || [];

  return NextResponse.json({ site, detail, perSiteAutomation, trend: dashboard.impact.monthly_trend });
}
