import { defineConfig, devices } from '@playwright/test'

// E2E config for the TBD2 frontend.
//
// Prereqs to run:  npx playwright install chromium   (one-time browser download)
// Then:            npm run test:e2e
//
// Expects the app on http://localhost:3100 (the `frontend-preview` launch config)
// and the backend on :8080. If a dev server is already running, it is reused.
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3100'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev -- --port 3100 --strictPort',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
