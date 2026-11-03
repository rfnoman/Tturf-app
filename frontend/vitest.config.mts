import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Vite 8 resolves tsconfig `paths` (our `@/*` alias) natively.
  resolve: { tsconfigPaths: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    // Playwright owns the e2e directory; Vitest must not try to run those specs.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
