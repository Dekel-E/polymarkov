import type { Config } from "tailwindcss";

// "Night desk" token system: cold blue-black ground, hairline panels, one
// instrument-amber accent for controls/dials. Green/red are reserved for
// data semantics (YES/NO, PnL) and come from Tailwind's emerald/red.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        desk: {
          deep: "#0B1017", // page ground
          panel: "#121A26", // cards
          raised: "#182335", // hover / raised surfaces
          line: "#243247", // hairlines & borders
          edge: "#33436b", // stronger borders (chips, inputs)
          ink: "#E7EDF4", // primary text
          soft: "#A9B6C6", // secondary text
          dim: "#7A889B", // tertiary text
          faint: "#516075", // captions / disabled
        },
        instrument: {
          DEFAULT: "#F0B441", // amber: controls, markers, labels
          bright: "#FFCB5C",
        },
      },
      fontFamily: {
        sans: ["var(--font-plex)", "system-ui", "sans-serif"],
        mono: ["var(--font-plex-mono)", "ui-monospace", "monospace"],
        display: ["var(--font-plex-cond)", "var(--font-plex)", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
