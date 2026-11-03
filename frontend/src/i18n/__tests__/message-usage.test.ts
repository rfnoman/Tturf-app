import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

import en from "../../../messages/en.json";

/**
 * Every `t("key")` in the app must resolve against `messages/en.json`.
 *
 * next-intl only fails at *render* time, and only on the branch that touches the
 * missing key — so a mistake like calling `t("common.yes")` inside a translator scoped
 * to `me` (which looks for `me.common.yes`) ships silently and surfaces as a blank page
 * for whoever hits that branch. Phase 01 found exactly that bug on `/me`. This scan is
 * static, so it catches the next one at `npm run test`.
 */

const SRC = join(__dirname, "../..");

/** `const x = useTranslations("ns")` / `await getTranslations("ns")`, or unscoped. */
const TRANSLATOR =
  /(?:const|let)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*(?:"([^"]*)"|'([^']*)')?\s*\)/g;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      return entry === "__tests__" ? [] : sourceFiles(path);
    }
    return /\.tsx?$/.test(path) && !path.endsWith(".d.ts") ? [path] : [];
  });
}

function resolves(key: string): boolean {
  let node: unknown = en;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null) return false;
    node = (node as Record<string, unknown>)[part];
    if (node === undefined) return false;
  }
  // ICU arguments mean a message can be any string; nested objects are namespaces,
  // which `t()` cannot render.
  return typeof node === "string";
}

type Usage = { file: string; translator: string; key: string };

/** Drop comments so prose examples of a `t("…")` call are not scanned as code. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

function usages(path: string): Usage[] {
  const source = stripComments(readFileSync(path, "utf8"));
  const scopes = new Map<string, string>();
  for (const match of source.matchAll(TRANSLATOR)) {
    scopes.set(match[1], match[2] ?? match[3] ?? "");
  }
  if (scopes.size === 0) return [];

  const found: Usage[] = [];
  for (const [name, namespace] of scopes) {
    // Only literal keys can be checked; template literals are skipped deliberately.
    const call = new RegExp(`\\b${name}\\(\\s*"([^"\`$]+)"`, "g");
    for (const match of source.matchAll(call)) {
      found.push({
        file: relative(SRC, path),
        translator: name,
        key: namespace ? `${namespace}.${match[1]}` : match[1],
      });
    }
  }
  return found;
}

describe("message usage", () => {
  const all = sourceFiles(SRC).flatMap(usages);

  it("finds the translator calls to check", () => {
    // A refactor that breaks the scan must fail loudly rather than silently pass.
    expect(all.length).toBeGreaterThan(20);
  });

  it("resolves every literal key against en.json", () => {
    const missing = all.filter((usage) => !resolves(usage.key));
    expect(
      missing.map((usage) => `${usage.file}: ${usage.translator}("…") -> ${usage.key}`),
    ).toEqual([]);
  });
});
