import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  define: {
    __OFM_SERVER_URL__: JSON.stringify(process.env.OFM_SERVER_URL || ""),
    // FPScanner encryption key — must match the backend's FPSCANNER_KEY
    __FP_ENCRYPTION_KEY__: JSON.stringify(process.env.FPSCANNER_KEY || "dev-key"),
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
