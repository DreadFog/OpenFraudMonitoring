import { defineConfig } from "vite";

export default defineConfig({
  define: {
    __OFM_SERVER_URL__: JSON.stringify(process.env.OFM_SERVER_URL || ""),
  },
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
