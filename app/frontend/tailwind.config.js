/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Color palette: editorial black/white with high contrast.
        // Slightly tinted neutrals (no pure #000/#fff).
        ink: "#0E0E10",        // "preto" tintado — footer, texto forte, botões
        carbon: "#1A1A1D",     // superfícies escuras
        paper: "#F7F6F4",      // "branco" tintado — fundo claro
        line: "#E3E1DD",       // bordas sutis em fundo claro
        lineDark: "#2C2C31",   // bordas em superfícies escuras
        muted: "#6B6A67",      // texto secundário sobre paper
        mutedDark: "#9C9BA0",  // texto secundário sobre ink
        // Cor só onde carrega significado (grades / sentimento)
        good: "#1F7A4D",
        warn: "#B87514",
        bad: "#B23A32",
      },
      fontFamily: {
        display: ["Archivo", "system-ui", "sans-serif"],
        sans: ["Public Sans", "system-ui", "sans-serif"],
      },
      maxWidth: {
        content: "1200px",
      },
    },
  },
  plugins: [],
};
