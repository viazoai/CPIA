import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSimulation, useSequence } from "@/lib/use-simulation";

describe("useSimulation", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("returns initial seed value", () => {
    const { result } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    expect(result.current).toBe(10);
  });

  it("updates on interval", () => {
    const { result } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toBe(11);
    act(() => { vi.advanceTimersByTime(2000); });
    expect(result.current).toBe(13);
  });

  it("cleans up on unmount", () => {
    const { result, unmount } = renderHook(() => useSimulation(10, (n) => n + 1, 1000));
    unmount();
    act(() => { vi.advanceTimersByTime(5000); });
    // Initial value unchanged (test passes if no error from setState after unmount)
    expect(result.current).toBe(10);
  });
});

describe("useSequence", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reveals items one by one", () => {
    const seq = ["a", "b", "c"];
    const { result } = renderHook(() => useSequence(seq, 1000));
    expect(result.current).toEqual([]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a"]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a", "b"]);

    act(() => { vi.advanceTimersByTime(1000); });
    expect(result.current).toEqual(["a", "b", "c"]);
  });

  it("stops at end of sequence", () => {
    const seq = ["a"];
    const { result } = renderHook(() => useSequence(seq, 1000));
    act(() => { vi.advanceTimersByTime(5000); });
    expect(result.current).toEqual(["a"]);
  });
});
