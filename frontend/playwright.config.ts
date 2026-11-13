import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command:
        process.platform === "win32"
          ? "..\backend\.venv\Scripts\python -m uvicorn app.main:app --port 8000"
          : "../backend/.venv/bin/python -m uvicorn app.main:app --port 8000",
      cwd: "../backend",
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
