import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  expect: {
    timeout: 7_000
  },
  fullyParallel: false,
  outputDir: "../output/playwright/test-results",
  reporter: [
    ["list"],
    ["html", { outputFolder: "../output/playwright/html-report", open: "never" }]
  ],
  use: {
    baseURL: "http://127.0.0.1:3001",
    acceptDownloads: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure"
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 3001 --strictPort",
    url: "http://127.0.0.1:3001",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
