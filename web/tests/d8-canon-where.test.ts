/**
 * D8 CANON-WHERE drift guard
 *
 * 불변식: 좌측 카드(wbsTreeBuild activity_agg)와 우측 누적뷰(registered/route.ts)는
 * 동일한 WHERE 조건(CANON WHERE)으로 mapper_activities 를 필터한다.
 * 두 파일의 조건 문자열이 달라지면 좌측 distinct-l7.5 수 ≠ 우측 누적 행수가 되어 D8 깨짐.
 *
 * DB 없이 소스 텍스트 수준에서 잠근다.
 * - transforms.ts (wbsTreeBuild activity_agg WHERE)
 * - app/api/mock/review/registered/route.ts (누적뷰 WHERE)
 * 두 파일 모두 세 가지 술어를 포함해야 한다.
 */

import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..");

function readSrc(relPath: string): string {
  return fs.readFileSync(path.join(ROOT, relPath), "utf-8");
}

const transformsSrc = readSrc("lib/transforms.ts");
const registeredSrc = readSrc("app/api/mock/review/registered/route.ts");

describe("D8 CANON-WHERE drift guard — activity_agg vs registered/route.ts", () => {
  // requires_review = FALSE — 두 파일 모두 포함해야 한다.
  it("transforms.ts activity_agg contains: requires_review = FALSE", () => {
    expect(transformsSrc).toContain("ma.requires_review = FALSE");
  });
  it("registered/route.ts contains: requires_review = FALSE", () => {
    expect(registeredSrc).toContain("ma.requires_review = FALSE");
  });

  // l6_main IS NOT NULL — 두 파일 모두 포함해야 한다.
  it("transforms.ts activity_agg contains: l6_main IS NOT NULL", () => {
    expect(transformsSrc).toContain("ma.l6_main IS NOT NULL");
  });
  it("registered/route.ts contains: l6_main IS NOT NULL", () => {
    expect(registeredSrc).toContain("ma.l6_main IS NOT NULL");
  });

  // trade 필터 — 각 파일의 실제 형식(공백 차이)을 그대로 단언.
  // transforms.ts: IN ('건축', '토목')  (쉼표 뒤 공백 있음)
  // registered/route.ts: IN ('건축','토목') (쉼표 뒤 공백 없음)
  // 의미는 동일. 형식 차이가 생겼을 때 이 주석이 경고 역할을 한다.
  it("transforms.ts activity_agg: trade IN 건축 토목 포함 (space variant)", () => {
    // 공백 있는 형태로 저장돼 있음
    expect(transformsSrc).toContain("ma.trade IN ('건축', '토목')");
  });
  it("registered/route.ts: trade IN 건축 토목 포함 (no-space variant)", () => {
    // 공백 없는 형태로 저장돼 있음
    expect(registeredSrc).toContain("ma.trade IN ('건축','토목')");
  });

  it("두 파일의 requires_review 방향이 동일 (양쪽 모두 = FALSE)", () => {
    // 혹시 한쪽이 = TRUE 로 바뀌면 D8 깨짐.
    // transforms.ts 의 activity_agg 블록에 = FALSE 가 있고 = TRUE 가 없어야 한다.
    // (review_agg 블록에는 = TRUE 가 있으므로 전체 파일 contains 로는 구분 불가 — 블록 스니핑)
    const activityAggBlock = transformsSrc.slice(
      transformsSrc.indexOf("activity_agg AS ("),
      transformsSrc.indexOf("forecast_agg AS ("),
    );
    expect(activityAggBlock).toContain("ma.requires_review = FALSE");
    expect(activityAggBlock).not.toContain("ma.requires_review = TRUE");

    // registered/route.ts 에는 requires_review = TRUE 가 없어야 한다.
    expect(registeredSrc).not.toContain("requires_review = TRUE");
  });

  it("registered/route.ts trade 필터가 두 공종을 포함한다", () => {
    expect(registeredSrc).toContain("'건축'");
    expect(registeredSrc).toContain("'토목'");
  });
});
