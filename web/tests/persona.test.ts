import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePersona, isMenuVisible } from "@/lib/persona";

describe("persona store", () => {
  beforeEach(() => {
    usePersona.setState({ persona: "member" });
  });

  it("default is member", () => {
    const { result } = renderHook(() => usePersona());
    expect(result.current.persona).toBe("member");
  });

  it("toggle swaps persona", () => {
    const { result } = renderHook(() => usePersona());
    act(() => result.current.toggle());
    expect(result.current.persona).toBe("manager");
    act(() => result.current.toggle());
    expect(result.current.persona).toBe("member");
  });

  it("setPersona sets directly", () => {
    const { result } = renderHook(() => usePersona());
    act(() => result.current.setPersona("manager"));
    expect(result.current.persona).toBe("manager");
  });
});

describe("menu visibility", () => {
  it("member sees 4 menus, no dashboard", () => {
    expect(isMenuVisible("member", "home")).toBe(true);
    expect(isMenuVisible("member", "tasks")).toBe(true);
    expect(isMenuVisible("member", "review")).toBe(true);
    expect(isMenuVisible("member", "reports")).toBe(true);
    expect(isMenuVisible("member", "dashboard")).toBe(false);
  });

  it("manager sees all 5 menus", () => {
    expect(isMenuVisible("manager", "dashboard")).toBe(true);
    expect(isMenuVisible("manager", "home")).toBe(true);
  });
});
