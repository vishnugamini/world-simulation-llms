import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests",
  timeout: 45000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8766",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 1100 },
    trace: "retain-on-failure",
  },
  reporter: "list",
  webServer: {
    command:
      "uv run virtual-world --db .data/browser-tests.sqlite3 serve --port 8766",
    cwd: "..",
    url: "http://127.0.0.1:8766/api/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
