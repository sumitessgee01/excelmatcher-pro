/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primarybg: "#0F172A",
        surface: "#1E293B",
        borderc: "#334155",
        accent: "#3B82F6",
        success: "#22C55E",
        warning: "#EAB308",
        danger: "#EF4444",
        textc: "#F1F5F9",
        muted: "#94A3B8"
      },
      fontFamily: {
        ui: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"]
      }
    }
  },
  plugins: []
};
