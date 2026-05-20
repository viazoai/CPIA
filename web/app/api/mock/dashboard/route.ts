// /api/mock/dashboard — Dashboard 페이지 응답 contract.
// dashboard/page.tsx 는 { sites: Site[], dashboard: DashboardFixture } shape 을 기대.
// DashboardFixture = { performance: { fleet_kpi, fleet_trend?, site_sparklines? }, impact: {...} }
//
// 시연 fixture (data/mock_dashboard.json + data/mock_sites.json) 반환.
// fleet_trend / site_sparklines 가 비면 컴포넌트가 mulberry32 로 deterministic 생성.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const dashboard = await loadFixture("dashboard");
  const sites = await loadFixture("sites");
  return NextResponse.json({ sites, dashboard });
}
