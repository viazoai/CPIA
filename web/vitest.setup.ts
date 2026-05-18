import { vi } from "vitest";
vi.mock("@/lib/pg", () => ({ default: vi.fn() }));
