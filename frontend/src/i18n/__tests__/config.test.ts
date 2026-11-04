import { parse, type MessageFormatElement } from "@formatjs/icu-messageformat-parser";
import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";
import bn from "../../../messages/bn.json";
import { defaultLocale, isLocale, locales } from "../config";

function lookup(catalogue: unknown, key: string): unknown {
  return key.split(".").reduce<unknown>((node, part) => {
    return typeof node === "object" && node !== null
      ? (node as Record<string, unknown>)[part]
      : undefined;
  }, catalogue);
}

/**
 * Every argument an ICU message takes, with how it is used.
 *
 * Read from the parsed message rather than by regex: inside a `select` or `plural`, the
 * branch bodies are themselves messages wrapped in braces, so `{Hydration}` in
 * `{tag, select, hydration {Hydration}}` looks exactly like a placeholder to a regex
 * and is nothing of the kind. Option names (`one`, `other`, `pickup_at_turf`) are part
 * of the contract too — a translator who renames one silently loses that branch.
 */
function argumentsOf(message: string): string[] {
  const found: string[] = [];

  const walk = (elements: MessageFormatElement[]) => {
    for (const element of elements) {
      if (!("value" in element) || typeof element.value !== "string") continue;
      if (element.type === 0 /* literal */) continue;

      if ("options" in element && element.options) {
        for (const [option, { value }] of Object.entries(element.options)) {
          found.push(`${element.value}:${option}`);
          walk(value);
        }
      } else {
        found.push(element.value);
      }
    }
  };

  walk(parse(message));
  return found.sort();
}

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
      const value = lookup(en, key);
      return typeof value === "string" && value.trim() === "";
    });
    expect(empty).toEqual([]);
  });

  it("leave no Bangla string in English", () => {
    // Two kinds of hole this catches, both found in Phase 11: a key copied from English
    // and never translated, and — worse — a Bangla value left behind when the English
    // one was rewritten, so `nav.myBookings` read "My bookings" while English read
    // "Bookings" and `owner.empty` still promised "Turf registration arrives in Phase
    // 02". Comparing the two strings cannot see either; looking for Bengali script can.
    //
    // A translation may legitimately carry Latin (a brand, a unit, an ICU option name) —
    // what it may not do is carry no Bengali at all where the English has words.
    const bengali = /[\u0980-\u09FF]/;
    const latinLetter = /[A-Za-z]/;

    const untranslated = flatKeys(en).filter((key) => {
      const source = lookup(en, key);
      const target = lookup(bn, key);
      if (typeof source !== "string" || typeof target !== "string") return false;
      // Placeholders and `select` option names stay English by design.
      const prose = source.replace(/\{(\w+), (?:plural|select),/g, "").replace(/\{[^{}]*\}/g, "");
      return latinLetter.test(prose) && !bengali.test(target);
    });

    expect(untranslated).toEqual([]);
  });

  it("take the same arguments in both languages", () => {
    // A translation that drops `{turf}`, renames a `select` branch or loses a plural
    // category does not fail to compile — it renders a sentence with a hole in it, or
    // throws for one value of one variable. Phase 11 translated 700 strings by hand;
    // this is what makes that safe to do again.
    const mismatched = flatKeys(en).flatMap((key) => {
      const source = lookup(en, key);
      const target = lookup(bn, key);
      if (typeof source !== "string" || typeof target !== "string") return [];

      const wanted = argumentsOf(source);
      const got = argumentsOf(target);
      return JSON.stringify(wanted) === JSON.stringify(got)
        ? []
        : [`${key}: expected ${wanted.join(", ") || "none"}; bn has ${got.join(", ") || "none"}`];
    });

    expect(mismatched).toEqual([]);
  });
});
