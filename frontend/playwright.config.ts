import { defineConfig } from "@playwright/test";

// Requer API (:8000) e `npm run dev` (:5173) no ar, com `make bootstrap` feito. E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD no ambiente.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173", trace: "retain-on-failure" },
  projects: [{ name: "desktop", use: { viewport: { width: 1440, height: 900 } } }, { name: "mobile", use: { viewport: { width: 360, height: 740 } }, testMatch: /mobile\.spec\.ts/ }],
});
