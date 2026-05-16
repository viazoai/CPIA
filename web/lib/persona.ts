"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Persona } from "./types";

interface PersonaState {
  persona: Persona;
  setPersona: (p: Persona) => void;
  toggle: () => void;
}

export const usePersona = create<PersonaState>()(
  persist(
    (set, get) => ({
      persona: "member",
      setPersona: (p) => set({ persona: p }),
      toggle: () => set({ persona: get().persona === "member" ? "manager" : "member" }),
    }),
    { name: "cpia-persona" }
  )
);

// 페르소나별 메뉴 노출 정책
export const MENU_VISIBILITY: Record<Persona, readonly string[]> = {
  member: ["home", "tasks", "review", "reports"],
  manager: ["home", "tasks", "review", "reports", "dashboard"],
} as const;

export function isMenuVisible(persona: Persona, menu: string): boolean {
  return MENU_VISIBILITY[persona].includes(menu);
}
