import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import bn from "../../../messages/bn.json";
import { defaultLocale, isLocale, locales } from "../config";

function flatKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) =>
    flatKeys(child, prefix ? `${prefix}.${key}` : key),
  );
}

describe("locale config", () => {
  it("offers English and Bangla", () => {
    expect(locales).toEqual(["en", "bn"]);
    expect(defaultLocale).toBe("en");
  });

  it("recognises supported locales only", () => {
    expect(isLocale("bn")).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
  });
});

describe("message catalogues", () => {
  it("define exactly the same keys", () => {
    // A key present in one file and missing in the other throws at render time, so the
    // two catalogues are kept in lockstep from Phase 00 onwards.
    expect(flatKeys(bn).sort()).toEqual(flatKeys(en).sort());
  });

  it("leave no English string empty", () => {
    const empty = flatKeys(en).filter((key) => {
      const value = key.split(".").reduce<unknown>((acc, part) => {
        return typeof acc === "object" && acc !== null
          ? (acc as Record<string, unknown>)[part]
          : undefined;
      }, en);
      return typeof value === "string" && value.trim() === "";
    });
    expect(empty).toEqual([]);
  });
});
