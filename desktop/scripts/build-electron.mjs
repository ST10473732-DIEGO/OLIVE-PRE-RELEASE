import { build } from "vite";
for (const entry of ["main", "preload"]) {
  await build({
    configFile: false,
    build: {
      outDir: "out/electron",
      emptyOutDir: false,
      lib: {
        entry: `electron/${entry}/index.ts`,
        formats: ["cjs"],
        fileName: () => `${entry}.cjs`,
      },
      rollupOptions: { external: ["electron", /^node:/] },
    },
  });
}
