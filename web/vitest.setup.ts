import { vi } from "vitest";
vi.mock("@/lib/pg", () => ({ default: vi.fn() }));

// jsdom does not provide CSS.escape — polyfill for tests.
// ASCII 특수문자만 백슬래시 escape, 비ASCII(한글 등, charCode >= 0x80)는 그대로 둠
// → 네이티브 CSS.escape 동작 근사 (WBS id 의 `::`·한글 대응).
if (typeof CSS === "undefined" || typeof CSS.escape === "undefined") {
  (globalThis as Record<string, unknown>).CSS = {
    ...(typeof CSS !== "undefined" ? CSS : {}),
    escape: (value: string) =>
      value.replace(/[^\w-]/g, (ch) => (ch.charCodeAt(0) < 0x80 ? "\\" + ch : ch)),
  };
}
