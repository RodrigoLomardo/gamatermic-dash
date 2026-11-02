/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "var(--brand)", dark: "var(--brand-dark)", soft: "var(--brand-soft)" },
        accent: { DEFAULT: "var(--accent)", on: "var(--on-accent)", dark: "var(--accent-dark)", soft: "var(--accent-soft)" },
        surface: "var(--surface)",
        panel: "var(--panel)",
        line: "var(--line)",
        ink: { DEFAULT: "var(--ink)", soft: "var(--ink-soft)", mute: "var(--ink-mute)" },
        sidebar: "var(--sidebar)",
        "on-status": "var(--on-status)",
        ok: { DEFAULT: "var(--ok)", soft: "var(--ok-soft)", ink: "var(--ok-ink)" },
        warn: { DEFAULT: "var(--warn)", soft: "var(--warn-soft)", ink: "var(--warn-ink)" },
        danger: { DEFAULT: "var(--danger)", soft: "var(--danger-soft)", ink: "var(--danger-ink)" },
      },
      fontFamily: { sans: ['"Inter Variable"', "system-ui", "sans-serif"], display: ['"Public Sans Variable"', "system-ui", "sans-serif"] },
      boxShadow: { card: "var(--shadow-card)" },
    },
  },
  plugins: [],
};
