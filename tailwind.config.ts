import type { Config } from "tailwindcss";

// "Luminous Terminal" token system: cool near-black ground, hairline panels,
// one electric-cyan signal accent for controls, live data and markers.
// Green/red stay reserved for data semantics (YES/NO, PnL) from Tailwind's
// emerald/red; amber is kept only for warnings. Token NAMES are stable
// (desk-* / instrument) so the whole surface recolors from here.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        desk: {
          deep: "#06080C", // page ground — cool near-black
          panel: "#0B0F16", // cards
          raised: "#131926", // hover / raised surfaces
          line: "#1B2531", // hairlines & borders
          edge: "#2A3644", // stronger borders (chips, inputs)
          ink: "#EAF1F8", // primary text
          soft: "#A6B3C4", // secondary text
          dim: "#6E7D90", // tertiary text
          faint: "#495768", // captions / disabled
        },
        instrument: {
          DEFAULT: "#22E1E6", // electric cyan: controls, markers, live data
          bright: "#6FF2F5",
          dim: "#128B90",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgb(34 225 230 / 0.25), 0 0 22px -6px rgb(34 225 230 / 0.55)",
        "glow-lg": "0 0 0 1px rgb(34 225 230 / 0.3), 0 0 40px -8px rgb(34 225 230 / 0.6)",
        lift: "0 12px 30px -14px rgb(0 0 0 / 0.7)",
      },
    },
  },
  plugins: [],
};

export default config;
