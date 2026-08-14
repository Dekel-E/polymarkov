import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = defineConfig([
  ...nextVitals,
  ...nextTypescript,
  globalIgnores([
      ".next/**",
      ".github/**",
      ".impeccable/**",
      ".venv/**",
      "node_modules/**",
      "next-env.d.ts",
      "backend/**",
      "api/**",
      "jobs/**",
      "scripts/**",
  ]),
  {
    rules: {
      // These components intentionally reset loading/search state while
      // synchronizing with remote APIs and browser storage.
      "react-hooks/set-state-in-effect": "off",
      // EquityChart deliberately anchors its final point to the wall clock.
      "react-hooks/purity": "off",
    },
  },
]);

export default config;
