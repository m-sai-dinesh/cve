import type { Config } from "tailwindcss";

/**
 * ModernRx design tokens.
 *
 * The GxP tier colours carry meaning, so they are defined once here and never
 * written as ad-hoc hex values in a component. PRD §18 requires the red/amber/
 * green scale to be accompanied by an icon or a label, never colour alone - the
 * `TierBadge` component enforces that.
 */
const config: Config = {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        raised: "rgb(var(--raised) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        high: "rgb(var(--high) / <alpha-value>)",
        "high-soft": "rgb(var(--high-soft) / <alpha-value>)",
        medium: "rgb(var(--medium) / <alpha-value>)",
        "medium-soft": "rgb(var(--medium-soft) / <alpha-value>)",
        low: "rgb(var(--low) / <alpha-value>)",
        "low-soft": "rgb(var(--low-soft) / <alpha-value>)",
        info: "rgb(var(--info) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      borderRadius: { xl: "0.75rem", "2xl": "1rem" },
      boxShadow: {
        card: "0 1px 2px rgb(0 0 0 / 0.04), 0 4px 12px -4px rgb(0 0 0 / 0.08)",
        pop: "0 8px 32px -8px rgb(0 0 0 / 0.22)",
      },
      keyframes: {
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgb(var(--accent) / 0.4)" },
          "70%": { boxShadow: "0 0 0 10px rgb(var(--accent) / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(var(--accent) / 0)" },
        },
      },
      animation: {
        "slide-up": "slide-up 0.25s ease-out both",
        shimmer: "shimmer 1.6s infinite",
        "pulse-ring": "pulse-ring 1.8s infinite",
      },
    },
  },
  plugins: [],
};
export default config;
