import { describe, expect, it } from "vitest";

import { clampScale, MAX_K, MIN_K } from "./viewport";

describe("clampScale", () => {
  it("keeps zoom within the range the canvas is legible at", () => {
    expect(clampScale(0)).toBe(MIN_K);
    expect(clampScale(100)).toBe(MAX_K);
    expect(clampScale(1)).toBe(1);
  });
});
