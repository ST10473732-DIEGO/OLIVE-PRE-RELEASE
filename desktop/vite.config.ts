import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "out/renderer",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // The Studio tooling store is shared by the eager App shell (which owns
        // the single event subscription) and the lazily loaded Studio chunk.
        // Keep it in one module so both see the same store instance.
        manualChunks: (id) =>
          id.includes("features/studio/tooling") ? "tooling" : undefined,
      },
    },
  },
  worker: { format: "es" },
});
