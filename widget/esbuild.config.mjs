import { build } from "esbuild";

// Produces a single, dependency-free IIFE — the file the installation
// snippet's <script src="..."> points at. No external requests at bundle
// time, no CDN dependency: everything the widget needs is inlined here.
await build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  outfile: "dist/widget.js",
  legalComments: "none",
});

console.log("Built dist/widget.js");
