import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

const local = fileURLToPath(new URL("./node_modules/", import.meta.url));
const dashboard = fileURLToPath(new URL("../../../dashboard/node_modules/", import.meta.url));
const modules = existsSync(`${local}vitest`) ? local : dashboard;

export default {
  resolve: {
    alias: [
      { find: "react/jsx-runtime", replacement: `${modules}react/jsx-runtime.js` },
      { find: "react", replacement: `${modules}react/index.js` },
    ],
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
};
