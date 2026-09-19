import { defineConfig } from "@playwright/test";
// Visual evidence capture only; not part of the ordinary e2e suite.
export default defineConfig({
  testDir: "tests/visual",
  timeout: 600000,
  workers: 1,
  reporter: "list",
});
