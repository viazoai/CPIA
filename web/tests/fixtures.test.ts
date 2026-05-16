import { describe, it, expect } from "vitest";
import { loadFixture } from "@/lib/fixtures";

describe("loadFixture", () => {
  it("loads existing mock_sites.json", async () => {
    const sites = await loadFixture("sites");
    expect(Array.isArray(sites)).toBe(true);
    expect(sites.length).toBeGreaterThan(0);
  });

  it("throws on missing fixture", async () => {
    await expect(loadFixture("nonexistent" as any)).rejects.toThrow();
  });
});
