import { test, expect } from "@playwright/test";

/**
 * Task 6 — reports 페이지 real DB 4 영역 노출 검증.
 *
 * 전제: dev 서버가 real PG (5532 prod tunnel) 에 접근 가능 + 최소 1 cycle 완료.
 * 기존 reports.spec.ts 가 mock_report.json intercept 라 real data 시각 검증 보조 못함 — 본 spec 으로 보완.
 *
 * selector 는 기존 reports.spec.ts 패턴 따름 (data-testid 미박힘, 텍스트/recharts class 기반).
 */

test.describe("/reports — real DB 4 영역", () => {
  test("§ 01 contractor bar 1개 이상 + CPI/SPI chip 표시 (mapper MH 산식 정상)", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    await page.waitForFunction(
      () => !document.body.innerText.includes("Loading..."),
      { timeout: 15000 },
    );

    // CPI/SPI chip
    await expect(page.locator("text=/CPI/").first()).toBeVisible();
    await expect(page.locator("text=/SPI/").first()).toBeVisible();

    // recharts bar — contractor 또는 trade
    const barCount = await page.locator(".recharts-bar").count();
    expect(barCount).toBeGreaterThanOrEqual(1);
  });

  test("§ 02 4분면 점 클릭 시 진단 4 영역 텍스트 노출 (by_wp dict lookup)", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    await page.waitForFunction(
      () => !document.body.innerText.includes("Loading..."),
      { timeout: 15000 },
    );

    // 4분면 산점도의 첫 점 클릭 — recharts ScatterChart 의 symbol
    const firstScatterPoint = page.locator(".recharts-scatter-symbol").first();
    await firstScatterPoint.click({ timeout: 5000 });

    // OptimizerResult 4 영역 (진단/유사 과거 사례/권고사항/상세 현황) 의 헤더 텍스트
    await expect(page.locator("text=진단").first()).toBeVisible();
    await expect(page.locator("text=유사 과거 사례").first()).toBeVisible();
    await expect(page.locator("text=권고사항").first()).toBeVisible();
    await expect(page.locator("text=상세 현황").first()).toBeVisible();

    // negative — EMPTY_OPTIMIZER fallback / cold_start 메시지 비노출 (실 데이터 채워짐)
    await expect(page.locator("text=진단 데이터 없음")).not.toBeVisible();
    await expect(page.locator("text=유사 사례 없음")).not.toBeVisible();
  });

  test("§ 03 ForecastChart recovery 곡선 노출 (scenarios 어댑터)", async ({ page }) => {
    await page.goto("/reports");
    await page.waitForLoadState("networkidle");
    await page.waitForFunction(
      () => !document.body.innerText.includes("Loading..."),
      { timeout: 15000 },
    );

    // ForecastChart 의 recovery 곡선 — recharts line/area 다수 중 최소 1개 visible
    const lineCount = await page.locator(".recharts-line").count();
    const areaCount = await page.locator(".recharts-area").count();
    expect(lineCount + areaCount).toBeGreaterThan(0);
  });
});
