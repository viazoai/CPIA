// 슬라이드 발표 모드 — 슬라이드별 PNG 캡처.
// 사용: cd web && LANDING_URL=http://localhost:5536/ node scripts/capture_slides.mjs
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const URL = process.env.LANDING_URL || "http://localhost:5535/";
const OUT_DIR = path.resolve(__dirname, "../../docs/landing-reference/slides");
const VIEWPORT = { width: 1440, height: 900 };
const SLIDE_NAMES = [
  "01-hero",
  "02-background",
  "03-as-is-to-be",
  "04-core-ai",
  "05-impact",
  "06-scalability",
  "07-final-cta",
];

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  console.log(`→ open ${URL}`);
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector(".presentation-mode", { timeout: 5000 });
  await page.waitForTimeout(800);

  for (let i = 0; i < SLIDE_NAMES.length; i++) {
    if (i > 0) {
      await page.keyboard.press("ArrowDown");
      // 전환 (700ms) + entrance 애니메이션 (~800ms) 대기.
      await page.waitForTimeout(1600);
    }
    const out = path.join(OUT_DIR, `${SLIDE_NAMES[i]}.png`);
    await page.screenshot({ path: out, type: "png" });
    console.log(`✓ ${out}`);
  }

  await browser.close();
  console.log(`\nDone. → ${OUT_DIR}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
