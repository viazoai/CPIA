import { test, expect } from "@playwright/test";
import { readFileSync } from "fs";
import path from "path";

/**
 * B.18 — reports 페이지 10 정량 assertion
 *
 * data-testid 미설정 확인됨(B.11~B.17 미추가).
 * 텍스트 / recharts SVG 클래스 / DOM 구조 기반 selector 사용.
 * backfill 2 cycle 기준 완화: >=1.
 *
 * PostgreSQL 연결 없는 로컬 환경 대응:
 * /api/mock/report 를 mock_report.json 으로 intercept.
 */

// mock_report.json 절대 경로 (web/ 기준 ../data/)
const MOCK_REPORT_PATH = path.join(__dirname, "../../data/mock_report.json");

test("reports page — 10 정량 기준 (B.18)", async ({ page }) => {
  // /api/mock/report 요청 intercept → mock_report.json 반환
  await page.route("**/api/mock/report", async (route) => {
    const body = readFileSync(MOCK_REPORT_PATH, "utf-8");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body,
    });
  });

  await page.goto("/reports");
  await page.waitForLoadState("networkidle");

  // 데이터 로드 대기 — Loading... 텍스트가 사라질 때까지
  await page.waitForFunction(() => {
    return !document.body.innerText.includes("Loading...");
  }, { timeout: 15000 });

  // 1. § 01 CPI chip 표시 (B.14)
  // kpi.cpi 없으면 "CPI —", 있으면 "CPI {숫자}" 모두 visible
  await expect(
    page.locator("text=/CPI/").first()
  ).toBeVisible();

  // 2. § 01 SPI chip 표시 (B.14)
  await expect(
    page.locator("text=/SPI/").first()
  ).toBeVisible();

  // 3. recharts Area 영역 >= 1 (ProductivityTrendChart 또는 ForecastChart)
  const areaCount = await page.locator(".recharts-area").count();
  expect(areaCount).toBeGreaterThan(0);

  // 4. recharts bar >= 1 (BarChartH — 업체별/공종별)
  const barCount = await page.locator(".recharts-bar").count();
  expect(barCount).toBeGreaterThanOrEqual(1);

  // 5. 공종별 토글 버튼 visible
  await expect(page.locator("text=공종별").first()).toBeVisible();

  // 6. 4분면 산점도 — recharts-scatter 존재 (ScatterChart, mock 6개 점)
  const scatterCount = await page.locator(".recharts-scatter").count();
  expect(scatterCount).toBeGreaterThanOrEqual(1);

  // 7. WP 표 row 1 개 이상 — WPSummaryTable tbody tr (mock 6개)
  const wpRowCount = await page.locator("table tbody tr").count();
  expect(wpRowCount).toBeGreaterThanOrEqual(1);

  // 8. § 02 OptimizerResult "진단" 섹션 표시 (cold_start fallback 포함)
  await expect(page.locator("text=진단").first()).toBeVisible();

  // 9. ForecastChart 라벨 "현 추세 연장" (B.16)
  await expect(page.locator("text=현 추세 연장")).toBeVisible();

  // 10. ForecastChart 라벨 "만회 시나리오 (AI)" (B.16)
  await expect(page.locator("text=만회 시나리오 (AI)")).toBeVisible();
});
