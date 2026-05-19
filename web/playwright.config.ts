import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:5536" },
  webServer: { command: "npm run dev", port: 5536, reuseExistingServer: true },
});
