import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    // Fetches the Clerk Testing Token once, so authenticated specs are not served a
    // bot-protection challenge they cannot clear.
    { name: "setup clerk", testMatch: /global\.setup\.ts/ },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup clerk"],
    },
    // Bangladesh is a mobile-first market; the shell must hold up at phone width.
    {
      name: "mobile",
      use: { ...devices["Pixel 7"] },
      dependencies: ["setup clerk"],
    },
  ],
  webServer: {
    // Always test the production build, never `next dev`. Turbopack's dev client boots
    // through its HMR WebSocket, and where that connection cannot be established the
    // page renders server-side but never hydrates — which looks exactly like a broken
    // component. `next start` has no such dependency, so results are deterministic and
    // identical to CI. Set PLAYWRIGHT_BASE_URL to point at an already-running server.
    command: "npm run build && npm run start",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
