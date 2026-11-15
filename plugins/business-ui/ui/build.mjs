import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { mkdir, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";

const require = createRequire(import.meta.url);
const esbuildPath = existsSync(
  fileURLToPath(new URL("../../../dashboard/node_modules/esbuild", import.meta.url)),
)
  ? "../../../dashboard/node_modules/esbuild"
  : "esbuild";
const { build } = require(esbuildPath);
const outputDir = fileURLToPath(new URL("./", import.meta.url));
await mkdir(outputDir, { recursive: true });
await build({
  entryPoints: [fileURLToPath(new URL("./src/index.ts", import.meta.url))],
  outfile: `${outputDir}index.js`,
  bundle: true,
  format: "esm",
  platform: "browser",
  target: ["es2022"],
  jsx: "automatic",
  jsxImportSource: "react",
  plugins: [
    {
      name: "host-react-shim",
      setup(buildApi) {
        buildApi.onResolve({ filter: /^react(?:\/jsx-runtime)?$/ }, (args) => ({
          path: args.path,
          namespace: "host-react",
        }));
        buildApi.onLoad({ filter: /.*/, namespace: "host-react" }, (args) => ({
          contents: args.path.endsWith("jsx-runtime")
            ? "const host = window.__OCTOP_JSX__; export const jsx = (...args) => host.jsx(...args); export const jsxs = (...args) => host.jsxs(...args); export const Fragment = window.__OCTOP_REACT__.Fragment;"
            : "const host = window.__OCTOP_REACT__; export const Fragment = host.Fragment; export const createElement = (...args) => host.createElement(...args); export const useCallback = (...args) => host.useCallback(...args); export const useEffect = (...args) => host.useEffect(...args); export const useMemo = (...args) => host.useMemo(...args); export const useRef = (...args) => host.useRef(...args); export const useState = (...args) => host.useState(...args);",
          loader: "js",
        }));
      },
    },
  ],
});
await writeFile(
  `${outputDir}manifest.json`,
  `${JSON.stringify(
    {
      renderers: [
        { id: "business_ui_card", tools: ["business_ui_draft"] },
        { id: "business_ui_config", tools: ["business_ui_connections"] },
      ],
    },
    null,
    2,
  )}\n`,
);
