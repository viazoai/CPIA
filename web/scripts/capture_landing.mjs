// 랜딩페이지 풀-페이지 + 섹션별 PNG 캡처.
// 사용: cd web && node scripts/capture_landing.mjs
// 출력: docs/landing-reference/*.png

import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const URL = process.env.LANDING_URL || "http://localhost:5535/";
const OUT_DIR = path.resolve(__dirname, "../../docs/landing-reference");
const VIEWPORT = { width: 1440, height: 900 };

// 컴포넌트 ↔ DOM 식별자 (LandingPage 순서 기준).
// Hero / AsIsToBe / Scalability / FinalCta 는 id 없음 → 자식 <section> 의 nth-child 로 잡는다.
const SECTIONS = [
  { name: "01-hero", selector: "main > section:nth-of-type(1)" },
  { name: "02-background", selector: "#background" },
  { name: "03-as-is-to-be", selector: "main > section:nth-of-type(3)" },
  { name: "04-core-ai", selector: "#ai-features" },
  { name: "05-impact", selector: "#impact" },
  { name: "06-scalability", selector: "main > section:nth-of-type(6)" },
  { name: "07-final-cta", selector: "main > section:nth-of-type(7)" },
];

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2, // retina 화질
  });
  const page = await ctx.newPage();

  console.log(`→ open ${URL}`);
  await page.goto(URL, { waitUntil: "networkidle" });

  // 폰트 + 이미지 + scroll-triggered 애니메이션 완전 로드.
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(async () => {
    // 페이지 전체 한 번 훑어 lazy element trigger.
    await new Promise((res) => {
      let y = 0;
      const step = window.innerHeight / 2;
      const t = setInterval(() => {
        window.scrollTo(0, y);
        y += step;
        if (y > document.body.scrollHeight) {
          clearInterval(t);
          window.scrollTo(0, 0);
          setTimeout(res, 400);
        }
      }, 80);
    });
  });
  await page.waitForTimeout(800);

  // 1) 전체 풀-페이지.
  const fullPath = path.join(OUT_DIR, "00-full-page.png");
  await page.screenshot({ path: fullPath, fullPage: true, type: "png" });
  console.log(`✓ ${fullPath}`);

  // 2) 섹션별.
  for (const s of SECTIONS) {
    const el = await page.$(s.selector);
    if (!el) {
      console.warn(`✗ ${s.name}: selector "${s.selector}" not found`);
      continue;
    }
    // 섹션이 viewport 안에 들어와야 lazy 콘텐츠가 정착함.
    await el.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    const out = path.join(OUT_DIR, `${s.name}.png`);
    await el.screenshot({ path: out, type: "png" });
    console.log(`✓ ${out}`);
  }

  await browser.close();
  console.log(`\nDone. → ${OUT_DIR}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
