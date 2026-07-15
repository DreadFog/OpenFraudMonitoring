import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  define: {
    __OFM_SERVER_URL__: JSON.stringify(process.env.OFM_SERVER_URL || ""),
    // FPScanner encryption key — must match the backend's FPSCANNER_KEY
    __FP_ENCRYPTION_KEY__: JSON.stringify(process.env.FPSCANNER_KEY || "dev-key"),
    // Debug mode — enables window.__OFM__ hooks for demo/debug pages
    __OFM_DEBUG__: process.env.OFM_DEBUG === "true",
    // Capture the actual copied/pasted clipboard text (off by default for privacy)
    __OFM_CAPTURE_CLIPBOARD__: process.env.OFM_CAPTURE_CLIPBOARD === "true",
  },
  resolve: {
    alias: {
      // Resolve fpscanner to its TypeScript source in the git submodule
      fpscanner: resolve(__dirname, "node_modules/fpscanner/src/index.ts"),
    },
  },
  build: {
    lib: {
      entry: "src/index.js",
      name: "OFMClient",
      formats: ["iife"],
      fileName: () => "ofm.js",
    },
    outDir: "dist",
    minify: false,
  },
});
