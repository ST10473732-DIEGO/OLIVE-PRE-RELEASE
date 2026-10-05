import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "out/renderer",
    emptyOutDir: true,
    // Fonts are always emitted as files: the renderer's CSP allows
    // font-src 'self' and blocks data: fonts. Other small assets may inline.
    assetsInlineLimit: (file) => (/\.(woff2?|ttf|otf)$/i.test(file) ? false : undefined),
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
  // The setup wizard embeds the Connect World self-host guide from the repository docs.
  server: { fs: { allow: [".", "../docs/connect-world"] } },
});
