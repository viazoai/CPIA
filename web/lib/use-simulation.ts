"use client";
import { useEffect, useState } from "react";

/**
 * Periodic transformation of a seed value.
 * Updates `value` every `intervalMs` ms by applying `updater(prev)`.
 *
 * Use for: counters that drift up/down (Home NOW strip "오늘 N건"),
 *          status that changes with time (Agent card processing count).
 */
export function useSimulation<T>(
  seed: T,
  updater: (prev: T) => T,
  intervalMs: number
): T {
  const [value, setValue] = useState(seed);
  useEffect(() => {
    const id = setInterval(() => setValue((p) => updater(p)), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, updater]);
  return value;
}

/**
 * Sequential reveal: incrementally exposes more items from `seq` over time.
 * After `intervalMs` ms, `revealed` has 1 item; after 2*intervalMs, 2 items; etc.
 *
 * Use for: Agent Tasks chat log new-message push,
 *          Forecast S-curve point-by-point reveal.
 */
export function useSequence<T>(seq: readonly T[], intervalMs: number): T[] {
  const [revealed, setRevealed] = useState<T[]>([]);
  useEffect(() => {
    setRevealed([]);
    if (seq.length === 0) return;
    let i = 0;
    const id = setInterval(() => {
      if (i >= seq.length) {
        clearInterval(id);
        return;
      }
      const current = i;
      i++;
      setRevealed((prev) => [...prev, seq[current]]);
    }, intervalMs);
    return () => clearInterval(id);
  }, [seq, intervalMs]);
  return revealed;
}
