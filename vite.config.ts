import { defineConfig } from "vite";

// Served from a custom domain root (msfs.razortek.nl), so base is "/".
// public/ (data.json + CNAME) is copied verbatim into dist/ on build.
export default defineConfig({
  base: "/",
  build: {
    outDir: "dist",
    target: "es2022",
  },
});
