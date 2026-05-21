// /api/mock/dashboard — Dashboard 페이지 응답 contract.
// dashboard/page.tsx 는 { sites: Site[], dashboard: DashboardFixture } shape 을 기대.
// DashboardFixture = { performance: { fleet_kpi, fleet_trend?, site_sparklines? }, impact: {...} }
//
// 시연 fixture (data/mock_dashboard.json + data/mock_sites.json) 반환.
// fleet_trend / site_sparklines 가 비면 컴포넌트가 mulberry32 로 deterministic 생성.

export const dynamic = "force-dynamic";

import { NextResponse } from "next/server";
import { loadFixture, loadReal } from "@/lib/fixtures";

export async function GET() {
  // Phase 2 (RC5): performance.fleet_kpi 를 PG 530일 평균으로 swap.
  // impact 는 fixture 유지 (hours_saved / fte_saved 는 PG 에 데이터 없음 — 후속 plan).
  const performance = await loadReal("dashboard_performance");
  const impactFixture = await loadFixture("dashboard");
  const dashboard = { performance, impact: impactFixture.impact };
  const sites = await loadFixture("sites");
  return NextResponse.json({ sites, dashboard });
}
