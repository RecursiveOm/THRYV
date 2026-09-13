import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "off",
    channel: "chromium",
    screenshot: "off",
    launchOptions: { args: ["--use-fake-device-for-media-stream"] },
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    {
      command:
        "uv run --inexact --project ../backend --directory ../backend uvicorn tests.e2e_server:app --host 127.0.0.1 --port 8001 --no-access-log",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
    },
    {
      command: "npm run dev -- --port 3001",
      url: "http://127.0.0.1:3001",
      env: {
        NEXT_PUBLIC_API_URL: "http://127.0.0.1:8001",
        NEXT_TELEMETRY_DISABLED: "1",
        THRYV_TEST_BUILD: "1",
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
