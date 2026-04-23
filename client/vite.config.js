import { defineConfig } from "vite";

export default defineConfig({
  build: {
    lib: {
      entry: "src/index.js",
      name: "FingerprintClient",
      formats: ["iife"],
      fileName: () => "fingerprint.js",
    },
    outDir: "dist",
    minify: false,
  },
});
