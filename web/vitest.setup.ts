import { vi } from "vitest";
vi.mock("@/lib/pg", () => ({ default: vi.fn() }));

// jsdom does not provide CSS.escape — polyfill for tests
if (typeof CSS === "undefined" || typeof CSS.escape === "undefined") {
  (globalThis as Record<string, unknown>).CSS = {
    ...(typeof CSS !== "undefined" ? CSS : {}),
    escape: (value: string) =>
      value.replace(/([^\w-])/g, "\\$1"),
  };
}
