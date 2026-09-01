/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1B3139",
        carbon: "#10272F",
        paper: "#F7F8FA",
        surface: "#FFFFFF",
        line: "#DCE0E2",
        lineDark: "#324850",
        muted: "#5D6B72",
        mutedDark: "#C3CDD1",
        brand: "#FF3621",
        brandDark: "#D62C1A",
        brandSoft: "#FFF0ED",
        good: "#227A52",
        warn: "#A86403",
        bad: "#C1352B",
      },
      fontFamily: {
        display: ["Aptos", "Segoe UI Variable", "Segoe UI", "system-ui", "sans-serif"],
        sans: ["Aptos", "Segoe UI Variable", "Segoe UI", "system-ui", "sans-serif"],
      },
      maxWidth: {
        content: "1280px",
      },
    },
  },
  plugins: [],
};
