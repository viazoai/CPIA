"""POC: F3 분포 + conditions + outlier 5% + l7.5 — 25-01-15 건축 1공종 in-memory.

scripts/poc_mock_redesign.py — brainstorming 단계 검증용 ad-hoc.
실 코드 적용 전 결정 사항 (F3 piecewise / conditions mapping / outlier 5% /
l7.5 채움 / l5_disc trade) 이 의도대로 작동하는지 656 row cross-section + 1 wbs
time series 두 가지로 검증.
"""

from __future__ import annotations

import asyncio
import hashlib
import random
from collections import Counter
from datetime import date, timedelta

import asyncpg

PG_URL = "postgresql://cpia:K7mP2xQ9nR4v@43.200.85.209:5532/cpia"
SITE = "m15x-ph3-ibl"
TARGET_DATE = date(2025, 1, 15)
TRADE = "건축"
ANCHOR_MH_PER_QTY = 5.1747  # legacy 참고용 (현재 미사용)
OUTLIER_PROB = 0.05
PROD_TARGET = 90.0  # 사용자 명시 — 생산성 타겟 90%, ±10% normal, 5% outlier 50/150

# F3 piecewise daily ratio (사용자 결정 — ramp 15% + plateau 70% + late-rise 15%, peak=1.5×plateau)
RAMP_END = 0.15
PLATEAU_END = 0.85
PEAK_MULT = 1.5
# integral over [0,1] = 0.5*0.15 + 0.70 + (1 + 1.5)/2 * 0.15 = 0.075 + 0.70 + 0.1875 = 0.9625
INTEGRAL = (
    0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + (1 + PEAK_MULT) / 2 * (1 - PLATEAU_END)
)
P_NORM = 1.0 / INTEGRAL  # ≈ 1.039

# diagnosis tag → conditions list (사용자 결정)
TAG_TO_CONDS = {
    "weather_rain": ["우천"],
    "manpower_short": ["인력부족"],
    "material_delay": ["자재미입고"],
    "rework": ["재작업"],
    "trade_overlap": ["병행작업"],
    "spec_change": ["사양변경"],
    "normal_steady": [],
}
TAGS = list(TAG_TO_CONDS.keys())


def f3_daily_ratio(progress: float) -> float:
    """progress (0~1) → daily ratio P_NORM normalized (integral = 1)."""
    if progress <= RAMP_END:
        return P_NORM * progress / RAMP_END
    if progress <= PLATEAU_END:
        return P_NORM
    return P_NORM * (
        1.0 + (progress - PLATEAU_END) / (1.0 - PLATEAU_END) * (PEAK_MULT - 1.0)
    )


def f3_cum_ratio(progress: float) -> float:
    """progress (0~1) → cumulative ratio (0~1)."""
    if progress <= RAMP_END:
        return 0.5 * progress * progress / RAMP_END * P_NORM
    if progress <= PLATEAU_END:
        return (0.5 * RAMP_END + (progress - RAMP_END)) * P_NORM
    u = progress - PLATEAU_END  # 0 ~ (1 - PLATEAU_END)
    late_part = u + 0.5 * (PEAK_MULT - 1.0) * u * u / (1.0 - PLATEAU_END)
    return (0.5 * RAMP_END + (PLATEAU_END - RAMP_END) + late_part) * P_NORM


def seeded_rng(seed_str: str) -> random.Random:
    h = hashlib.sha256(seed_str.encode("utf-8")).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def pick_tag(date_str: str, wa: str, company: str) -> str:
    idx = int(hashlib.md5(f"{date_str}|{wa}|{company}".encode()).hexdigest(), 16) % len(
        TAGS
    )
    return TAGS[idx]


async def main():
    conn = await asyncpg.connect(PG_URL)
    rows = await conn.fetch(
        """
        SELECT wa, l6_main, l7_5_activity, l5_disc, company, unit,
               plan_total_qty, plan_mh_rev2, plan_start, plan_finish
        FROM activity_master
        WHERE site_id = $1 AND l5_disc = $2
          AND plan_start <= $3 AND plan_finish >= $3
        ORDER BY plan_start, wa, company
        """,
        SITE,
        TRADE,
        TARGET_DATE,
    )
    print(f"=== 활성 row (25-01-15, l5_disc={TRADE}): {len(rows)} ===")

    sim_rows = []
    for r in rows:
        plan_total = float(r["plan_total_qty"] or 0)
        plan_mh = float(r["plan_mh_rev2"] or 0)
        if plan_total <= 0 or r["plan_finish"] is None or r["plan_start"] is None:
            continue
        total_days = (r["plan_finish"] - r["plan_start"]).days + 1
        days_elapsed = (TARGET_DATE - r["plan_start"]).days + 1
        progress = days_elapsed / total_days

        # F3 daily ratio (분포)
        ratio_today = f3_daily_ratio(progress)
        cum_frac = f3_cum_ratio(progress)

        # noise + outlier → actual_prod_pct (90% normal ±10% / 50 or 150 outlier 5%)
        rng = seeded_rng(f"{TARGET_DATE}|{r['wa']}|{r['company']}")
        is_outlier = rng.random() < OUTLIER_PROB
        if is_outlier:
            actual_prod_pct = rng.choice([50.0, 150.0])
        else:
            actual_prod_pct = PROD_TARGET * (1.0 + (rng.random() * 2 - 1) * 0.10)

        today_qty = (
            plan_total
            / total_days
            * ratio_today
            * (1.0 + (rng.random() * 2 - 1) * 0.10)
        )
        today_cum_qty = plan_total * cum_frac
        # cum_actual_mh = plan_mh × progress × actual_prod_pct / 100 (prod target 기반 역산)
        # 이전 today_cum_qty × ANCHOR_MH_PER_QTY 산출은 row 별 plan_mh_per_qty 편차
        # (0.28~1255) 를 그대로 노출 → prod 극단치 (0.4%~1750%). 새 산출은 prod 가
        # actual_prod_pct 그대로 (81~99 normal / 50 or 150 outlier).
        cum_actual_mh = plan_mh * progress * actual_prod_pct / 100.0

        # conditions
        tag = pick_tag(str(TARGET_DATE), r["wa"], r["company"])
        conditions = TAG_TO_CONDS[tag]

        # productivity (today_productivity = cum_actual_mh / expected_mh × 100)
        plan_mh_per_day = plan_mh / total_days if total_days > 0 else 0
        expected_mh = plan_mh_per_day * days_elapsed
        prod = (cum_actual_mh / expected_mh * 100) if expected_mh > 0 else 0.0

        sim_rows.append(
            {
                "wa": r["wa"],
                "l6": r["l6_main"],
                "l7_5": r["l7_5_activity"],
                "l5": r["l5_disc"],
                "company": r["company"],
                "unit": r["unit"],
                "plan_start": r["plan_start"],
                "plan_finish": r["plan_finish"],
                "plan_total": plan_total,
                "total_days": total_days,
                "days_elapsed": days_elapsed,
                "progress": progress,
                "ratio_today": ratio_today,
                "cum_frac": cum_frac,
                "today_qty": today_qty,
                "today_cum_qty": today_cum_qty,
                "cum_actual_mh": cum_actual_mh,
                "productivity": prod,
                "tag": tag,
                "conditions": conditions,
                "is_outlier": is_outlier,
            }
        )

    n = len(sim_rows)
    print("\n=== 656 row cross-section 분포 통계 ===")

    # 1. progress 분포 (656 row 가 F3 의 어느 구간에 분포해 있나)
    print("\n[1] progress (현재 진행 비율) 분포 — F3 어느 단계에서 cross-section?")
    bins = [
        (0.0, 0.15, "ramp"),
        (0.15, 0.30, "plat-early"),
        (0.30, 0.50, "plat-mid"),
        (0.50, 0.70, "plat-late"),
        (0.70, 0.85, "plat-end"),
        (0.85, 1.0, "late-rise"),
    ]
    for lo, hi, label in bins:
        cnt = sum(1 for s in sim_rows if lo <= s["progress"] < hi)
        bar = "█" * int(cnt / 3)
        print(f"  {lo:.2f}~{hi:.2f} ({label:11}): {cnt:4d}  {bar}")

    # 2. F3 daily ratio 적용 결과 (실 today_qty 가 plan/day 대비 어떤 배율인가)
    print("\n[2] F3 ratio_today 분포 (1.0 = plan 균등 일배분 기준)")
    for lo, hi in [
        (0.0, 0.3),
        (0.3, 0.6),
        (0.6, 0.9),
        (0.9, 1.1),
        (1.1, 1.3),
        (1.3, 1.6),
    ]:
        cnt = sum(1 for s in sim_rows if lo <= s["ratio_today"] < hi)
        bar = "█" * int(cnt / 3)
        print(f"  {lo:.2f}~{hi:.2f}: {cnt:4d}  {bar}")

    # 3. conditions tag 분포
    print("\n[3] conditions tag 분포 (해시 기반 결정성 7 tag)")
    tag_cnt = Counter(s["tag"] for s in sim_rows)
    for tag, cnt in tag_cnt.most_common():
        bar = "█" * int(cnt / 3)
        print(f"  {tag:16}  {cnt:4d}  ({cnt / n * 100:.1f}%)  {bar}")

    # 4. outlier 비율
    out_n = sum(1 for s in sim_rows if s["is_outlier"])
    print(f"\n[4] outlier row: {out_n}/{n} ({out_n / n * 100:.1f}%) — 목표 5%")

    # 5. productivity 분포
    prods = [s["productivity"] for s in sim_rows if s["productivity"] > 0]
    prods.sort()
    print(f"\n[5] productivity 분포 (n={len(prods)}):")
    print(
        f"  min: {prods[0]:.1f}, p5: {prods[len(prods) // 20]:.1f}, p25: {prods[len(prods) // 4]:.1f}, "
        f"median: {prods[len(prods) // 2]:.1f}, p75: {prods[len(prods) * 3 // 4]:.1f}, "
        f"p95: {prods[len(prods) * 19 // 20]:.1f}, max: {prods[-1]:.1f}"
    )
    print("  목표: 86% ± 10% normal + outlier (43% or 129%)")

    # 6. l7.5 sample
    print("\n[6] l7_5_activity sample 8:")
    for s in sim_rows[:8]:
        conds_s = ",".join(s["conditions"]) if s["conditions"] else "-"
        print(
            f"  [{s['l5']}] {s['l6']:30} > {s['l7_5']:30} | tag={s['tag']:14} cond={conds_s:10} prod={s['productivity']:.1f}%"
        )

    # 7. F3 daily ratio 함수 자체 검증
    print("\n[7] F3 daily_ratio(progress) 검증:")
    for p in [0.0, 0.05, 0.10, 0.15, 0.30, 0.50, 0.70, 0.85, 0.90, 0.95, 1.0]:
        print(
            f"  progress={p:.2f}  daily_ratio={f3_daily_ratio(p):.3f}  cum_frac={f3_cum_ratio(p):.3f}"
        )
    print(f"  integral check: f3_cum_ratio(1.0) = {f3_cum_ratio(1.0):.4f} (목표 1.0)")

    # 8. 1 wbs row plan_start ~ plan_finish 전 시계열
    sample = sim_rows[0]
    total_days = sample["total_days"]
    plan_total = sample["plan_total"]
    print(
        f"\n[8] 1 wbs row 전 구간 시계열 (sample wa={sample['wa']}, l7.5={sample['l7_5']})"
    )
    print(
        f"  plan_start={sample['plan_start']}, plan_finish={sample['plan_finish']}, plan_total={plan_total:.1f}, total_days={total_days}"
    )
    print("  day_offset  progress  ratio  expected_qty  cum_frac  cum_expected")
    step = max(1, total_days // 18)
    for offset in range(0, total_days, step):
        d = sample["plan_start"] + timedelta(days=offset)
        p = (offset + 1) / total_days
        r = f3_daily_ratio(p)
        q = plan_total / total_days * r
        cf = f3_cum_ratio(p)
        cq = plan_total * cf
        print(f"  {d}  {p:.3f}    {r:.3f}  {q:7.2f}      {cf:.3f}    {cq:8.2f}")

    await conn.close()

    # SVG 차트 저장 (visual companion 용)
    svg_path = "/Users/kyungseoplee/Project Agent/CPIA/.superpowers/brainstorm/89070-1779491542/poc-result.html"
    write_svg_report(sim_rows, sample, svg_path)
    print(f"\nSVG report → {svg_path}")


def write_svg_report(sim_rows: list, sample: dict, out_path: str) -> None:
    """결과 통계를 HTML/SVG 로 저장 (visual companion 화면)."""
    n = len(sim_rows)
    tag_cnt = Counter(s["tag"] for s in sim_rows)
    out_n = sum(1 for s in sim_rows if s["is_outlier"])
    prods = sorted([s["productivity"] for s in sim_rows if s["productivity"] > 0])

    # progress 히스토그램 SVG
    bins = [
        (0.0, 0.15),
        (0.15, 0.30),
        (0.30, 0.50),
        (0.50, 0.70),
        (0.70, 0.85),
        (0.85, 1.0),
    ]
    counts = [sum(1 for s in sim_rows if lo <= s["progress"] < hi) for lo, hi in bins]
    max_cnt = max(counts) if counts else 1

    bar_svg = ""
    for i, ((lo, hi), c) in enumerate(zip(bins, counts)):
        h = (c / max_cnt) * 100
        x = 30 + i * 50
        bar_svg += f'<rect x="{x}" y="{120 - h}" width="40" height="{h}" fill="rgba(102,200,160,.7)" stroke="#6c8"/>'
        bar_svg += f'<text x="{x + 20}" y="{125 - h - 4}" text-anchor="middle" fill="#cfc" font-size="8">{c}</text>'
        bar_svg += f'<text x="{x + 20}" y="135" text-anchor="middle" fill="#888" font-size="7">{lo:.2f}~{hi:.2f}</text>'

    # F3 daily_ratio curve SVG
    pts = []
    for i in range(101):
        p = i / 100
        y = 120 - f3_daily_ratio(p) / 1.6 * 100
        x = 30 + p * 360
        pts.append(f"{x:.1f},{y:.1f}")
    curve_path = "M " + " L ".join(pts)

    # tag 분포 막대
    tag_svg = ""
    sorted_tags = tag_cnt.most_common()
    max_tag = sorted_tags[0][1] if sorted_tags else 1
    for i, (tag, c) in enumerate(sorted_tags):
        w = (c / max_tag) * 220
        y = 30 + i * 22
        tag_svg += f'<rect x="120" y="{y - 12}" width="{w}" height="14" fill="rgba(255,200,100,.7)" stroke="#fc6"/>'
        tag_svg += f'<text x="115" y="{y - 1}" text-anchor="end" fill="#fff" font-size="10">{tag}</text>'
        tag_svg += f'<text x="{120 + w + 6}" y="{y - 1}" fill="#fff" font-size="10">{c} ({c / n * 100:.1f}%)</text>'

    html = (
        f"""<h2>POC 결과 — F3 분포 + conditions + outlier (25-01-15 건축 {n} row)</h2>
<p class="subtitle">in-memory 시뮬레이션. activity_master 656 row 활성. F3 / 5% outlier / 7 tag conditions 적용.</p>

<div class="section">
  <span class="label">[1] progress 분포 (656 row 가 F3 어느 단계에)</span>
  <svg viewBox="0 0 360 145" width="100%" style="max-width:560px;background:#1c1c1c;border-radius:8px;padding:8px">
    <line x1="20" y1="120" x2="340" y2="120" stroke="#666" stroke-width="0.5"/>
    {bar_svg}
  </svg>
</div>

<div class="section">
  <span class="label">[2] F3 daily_ratio 곡선 (적용 함수 자체)</span>
  <svg viewBox="0 0 400 145" width="100%" style="max-width:560px;background:#1c1c1c;border-radius:8px;padding:8px">
    <line x1="30" y1="120" x2="390" y2="120" stroke="#666" stroke-width="0.5"/>
    <line x1="84" y1="20" x2="84" y2="120" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>
    <line x1="336" y1="20" x2="336" y2="120" stroke="#666" stroke-width="0.3" stroke-dasharray="2,2"/>
    <path d="{curve_path}" fill="none" stroke="#fc6" stroke-width="1.5"/>
    <text x="84" y="135" text-anchor="middle" fill="#888" font-size="8">15% (ramp end)</text>
    <text x="336" y="135" text-anchor="middle" fill="#888" font-size="8">85% (late-rise)</text>
    <text x="210" y="115" text-anchor="middle" fill="#bbb" font-size="9">plateau ≈ 1.04</text>
    <text x="370" y="35" text-anchor="end" fill="#bbb" font-size="9">peak 1.56</text>
  </svg>
</div>

<div class="section">
  <span class="label">[3] conditions tag 분포 (7 종 해시 기반)</span>
  <svg viewBox="0 0 400 180" width="100%" style="max-width:560px;background:#1c1c1c;border-radius:8px;padding:8px">
    {tag_svg}
  </svg>
</div>

<div class="section">
  <span class="label">[4] outlier + productivity</span>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:6px">
    <tr><td style="padding:4px;width:160px">outlier row</td><td style="padding:4px">{out_n}/{n} ({out_n / n * 100:.1f}%) — 목표 5%</td></tr>
    <tr><td style="padding:4px">prod min/p5/median/p95/max</td><td style="padding:4px">{prods[0]:.1f} / {prods[len(prods) // 20]:.1f} / {prods[len(prods) // 2]:.1f} / {prods[len(prods) * 19 // 20]:.1f} / {prods[-1]:.1f}</td></tr>
    <tr><td style="padding:4px">활성 row 총</td><td style="padding:4px">{n}</td></tr>
  </table>
</div>

<div class="section">
  <span class="label">[5] l7_5_activity sample 5 row</span>
  <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:6px">
    <thead><tr style="border-bottom:1px solid rgba(255,255,255,.1)">
      <th style="padding:4px;text-align:left">l5</th><th style="padding:4px;text-align:left">l6_main</th>
      <th style="padding:4px;text-align:left">l7_5_activity</th><th style="padding:4px;text-align:left">tag</th>
      <th style="padding:4px;text-align:left">cond</th><th style="padding:4px;text-align:right">prod</th></tr></thead>
    <tbody>
"""
        + "".join(
            f'      <tr><td style="padding:4px">{s["l5"]}</td><td style="padding:4px">{s["l6"]}</td>'
            f'<td style="padding:4px">{s["l7_5"]}</td><td style="padding:4px">{s["tag"]}</td>'
            f'<td style="padding:4px">{",".join(s["conditions"]) or "-"}</td>'
            f'<td style="padding:4px;text-align:right">{s["productivity"]:.1f}%</td></tr>\n'
            for s in sim_rows[:5]
        )
        + """    </tbody>
  </table>
</div>
"""
    )
    with open(out_path, "w") as f:
        f.write(html)


if __name__ == "__main__":
    asyncio.run(main())
