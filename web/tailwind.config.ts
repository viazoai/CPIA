import type { Config } from "tailwindcss";

/**
 * CPIA 디자인 토큰 — v7.1 시안 기반.
 * 색은 light(연한 배경) / DEFAULT(짙은 강조) / text(어두운 텍스트) 3 톤 구조.
 * 사용 예: bg-mint-light text-mint-text · bg-lavender · text-rose-text
 */
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
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
        border: {
          DEFAULT: "var(--border)",
          soft: "var(--border-soft)",
        },
        mint: {
          light: "var(--mint)",
          DEFAULT: "var(--mint-deep)",
          text: "var(--mint-text)",
        },
        lavender: {
          light: "var(--lavender)",
          DEFAULT: "var(--lavender-deep)",
          text: "var(--lavender-text)",
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
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "Noto Sans KR",
          "var(--font-noto)",
          "system-ui",
          "sans-serif",
        ],
        display: [
          "Space Grotesk",
          "var(--font-display)",
          "Pretendard",
          "system-ui",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
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
    },
  },
  plugins: [],
};

export default config;
