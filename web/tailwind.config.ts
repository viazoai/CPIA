import type { Config } from "tailwindcss";

/**
 * CPIA 디자인 토큰 — v7.1 시안 기반 + shadcn/ui 호환.
 *   - v7.1 색: bg-mint-light · text-mint-text · ring-lavender 등
 *   - shadcn 색: bg-primary · text-destructive 등 (HSL 변수 매핑)
 *   - 폰트: font-sans (본문) · font-display (헤더) · font-mono (라벨·코드)
 *   - radius: rounded-card · rounded-card-lg · rounded-card-xl
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1240px" },
    },
    extend: {
      // QHD 전용 표시용 커스텀 breakpoint. FHD(1920)·FHD@125%(1536)는 미달,
      // QHD(2560)·QHD@125%(2048)는 도달 → `qhd:` 유틸로 QHD에서만 노출되는 요소 제어.
      screens: { qhd: "2048px" },
      colors: {
        /* v7.1 의미 색 — 직접 named 토큰 */
        ink: {
          DEFAULT: "var(--ink)",
          mid: "var(--ink-mid)",
          light: "var(--ink-light)",
        },
        surface: {
          DEFAULT: "var(--bg)",
          card: "var(--bg-card)",
          soft: "var(--bg-soft)",
        },
        mint: {
          light: "var(--mint)",
          DEFAULT: "var(--mint-deep)",
          text: "var(--mint-text)",
        },
        brand: {
          light: "var(--brand)",
          DEFAULT: "var(--brand-deep)",
          text: "var(--brand-text)",
        },
        peach: {
          light: "var(--peach)",
          DEFAULT: "var(--peach-deep)",
          text: "var(--peach-text)",
        },
        sky: {
          light: "var(--sky)",
          DEFAULT: "var(--sky-deep)",
          text: "var(--sky-text)",
        },
        sun: {
          light: "var(--sun)",
          DEFAULT: "var(--sun-deep)",
          text: "var(--sun-text)",
        },
        rose: {
          light: "var(--rose)",
          DEFAULT: "var(--rose-deep)",
          text: "var(--rose-text)",
        },

        /* shadcn 표준 색 — HSL CSS 변수 매핑.
         * border 는 객체로: border-border (DEFAULT) + border-border-soft 둘 다 풀리도록 */
        border: {
          DEFAULT: "hsl(var(--border))",
          soft: "var(--border-soft)",
        },
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      /* fontFamily — next/font 의 CSS variable 의존을 제거.
       * CSS 의 var(--x) 가 undefined 면 전체 font-family declaration 이
       * invalid 처리되어 fallback 이 깨지므로, jsdelivr CDN 으로 로드한
       * 실제 폰트 이름을 직접 chain 으로 둔다. */
      fontFamily: {
        sans: ["Pretendard", "Noto Sans KR", "system-ui", "sans-serif"],
        display: ["Inter Tight", "Pretendard", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      /* ──────────────────────────────────────────────────────────────────
       * 타입 스케일 — docs/ui/sample/font.png 단일 출처.
       *   각 토큰 = [size, { lineHeight, letterSpacing, fontWeight }]
       *   Tailwind 기본 text-xs..text-9xl 은 그대로 사용 가능(extend).
       *   새 코드에서는 임의 text-Nxl 대신 의미 토큰 사용 권장.
       * ────────────────────────────────────────────────────────────────── */
      fontSize: {
        "h1":      ["3.875rem", { lineHeight: "4.375rem", letterSpacing: "-0.02em",  fontWeight: "500" }],
        "h2":      ["3.25rem",  { lineHeight: "3.75rem",  letterSpacing: "-0.015em", fontWeight: "500" }],
        "h3":      ["2.625rem", { lineHeight: "3.125rem", letterSpacing: "-0.015em", fontWeight: "500" }],
        "h4":      ["1.75rem",  { lineHeight: "2.125rem", letterSpacing: "-0.005em", fontWeight: "500" }],
        "h5":      ["1.25rem",  { lineHeight: "1.875rem", letterSpacing: "0",        fontWeight: "600" }],
        "h6":      ["1.125rem", { lineHeight: "1.6875rem",letterSpacing: "0",        fontWeight: "500" }],
        "body":    ["1.125rem", { lineHeight: "1.6875rem",letterSpacing: "0",        fontWeight: "400" }],
        "body-sm": ["1rem",     { lineHeight: "1.5rem",   letterSpacing: "0",        fontWeight: "400" }],
        "btn":     ["1.25rem",  { lineHeight: "1.875rem", letterSpacing: "-0.02em",  fontWeight: "500" }],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        card: "18px",
        "card-lg": "24px",
        "card-xl": "32px",
      },
      boxShadow: {
        xs: "var(--shadow-xs)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      maxWidth: {
        wrap: "1240px",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
