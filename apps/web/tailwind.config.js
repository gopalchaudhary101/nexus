/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0a0e14",
        surface: "#101724",
        raised: "#151f30",
        line: "#1e2a3d",
        accent: {
          DEFAULT: "#22d3ee",
          dim: "#0e7490",
        },
        violet: {
          glow: "#8b5cf6",
        },
        ink: {
          DEFAULT: "#e2e8f0",
          dim: "#8fa3bd",
          faint: "#5b6c85",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px rgba(34, 211, 238, 0.12)",
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px rgba(0,0,0,0.35)",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        pulseSoft: "pulseSoft 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
