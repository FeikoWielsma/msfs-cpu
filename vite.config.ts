import { defineConfig } from "vite";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// package.json is type:module, so the config is loaded as ESM and has no __dirname.
const here = dirname(fileURLToPath(import.meta.url));

// Served from a custom domain root (msfs.razortek.nl), so base is "/".
// public/ (data.json, builds.json + CNAME) is copied verbatim into dist/ on build.
//
// Three pages, not one app: index.html is the benchmark SPA, specs/index.html is the
// build guide at /specs, limited/index.html is the MainThread-vs-GPU toy at /limited.
// They share the palette (src/theme.css) and the theme setting and nothing else, and
// are bundled separately — no page pulls in another's code, and a change to one page
// cannot reflow the others.
export default defineConfig({
  base: "/",
  build: {
    outDir: "dist",
    target: "es2022",
    rollupOptions: {
      input: {
        main: resolve(here, "index.html"),
        specs: resolve(here, "specs/index.html"),
        limited: resolve(here, "limited/index.html"),
      },
    },
  },
});
