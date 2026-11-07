import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "ui.spec.ts",
  fullyParallel: true,
  reporter: "list",
  use: {
    channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL || undefined,
    baseURL: "http://127.0.0.1:5181",
    viewport: { width: 1320, height: 1100 },
  },
  webServer: {
    command: "npm exec vite -- --host 127.0.0.1 --port 5181",
    url: "http://127.0.0.1:5181",
    reuseExistingServer: !process.env.CI,
  },
});
