import { describe, expect, it } from "vitest";

import { ratingTone } from "../rating";

describe("ratingTone", () => {
  it("bands a rating into one of four tones", () => {
    const tones = [30, 55, 70, 85].map(ratingTone);
    expect(new Set(tones).size).toBe(4);
  });

  it("puts band boundaries where the design says", () => {
    expect(ratingTone(80)).toBe(ratingTone(99));
    expect(ratingTone(79)).toBe(ratingTone(65));
    expect(ratingTone(64)).toBe(ratingTone(50));
    expect(ratingTone(49)).toBe(ratingTone(1));
  });

  it("never returns an interpolated class name", () => {
    // Tailwind's JIT compiler cannot see dynamic class names, so every tone must be a
    // literal that appears in the source.
    for (const value of [1, 50, 65, 80, 99]) {
      expect(ratingTone(value)).not.toMatch(/\$\{|\[/);
    }
  });
});
