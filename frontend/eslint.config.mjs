import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import prettier from "eslint-config-prettier/flat";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  prettier,
  {
    // Playwright fixtures are declared as `async ({}, use) => …`, and the React Hooks
    // rule reads that `use` call as a misplaced React hook. No React runs in e2e specs.
    files: ["e2e/**/*.ts"],
    rules: { "react-hooks/rules-of-hooks": "off" },
  },
  // Spreading the shared configs drops their default ignores, so restate them.
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "coverage/**",
    "playwright-report/**",
    "test-results/**",
    // Generated from the backend OpenAPI schema; not ours to lint.
    "src/lib/api/schema.d.ts",
  ]),
]);
