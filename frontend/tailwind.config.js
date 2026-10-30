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
        ok: "var(--ok)",
        warn: "var(--warn)",
        danger: "var(--danger)",
      },
      fontFamily: { sans: ['"Inter Variable"', "system-ui", "sans-serif"], display: ['"Public Sans Variable"', "system-ui", "sans-serif"] },
      boxShadow: { card: "0 1px 2px rgba(14,42,71,.06), 0 4px 16px rgba(14,42,71,.06)" },
    },
  },
  plugins: [],
};
