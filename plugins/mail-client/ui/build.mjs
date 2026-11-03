import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const src = join(root, "src");
const dist = join(root, "dist");

mkdirSync(dist, { recursive: true });
copyFileSync(join(src, "index.js"), join(dist, "index.js"));
copyFileSync(join(src, "manifest.json"), join(dist, "manifest.json"));
console.log("mail-client ui: copied src → dist");
