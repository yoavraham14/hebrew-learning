/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // "Linguistic dusk" palette — deep indigo evening, warm ember spark
        // for the reveal/discovery moment, cool teal "bridge" for the
        // English bridge-language accent. Deliberately not cream+terracotta
        // or near-black+acid-green.
        ink: "#16142B", // page background
        surface: "#211E45", // card/surface background
        surfacemuted: "#2B2757", // secondary surface (badges, inputs)
        parchment: "#F6F0E4", // primary text — warm ivory, not stark white
        ember: "#F2994A", // primary accent: reveal, CTA, streak flame
        bridge: "#5EC8D8", // secondary accent: English bridge tag, links
        known: "#6FCF97", // "knew it" / success
        almost: "#F2C94C", // "almost" rating
        danger: "#E85C4A", // "didn't know" rating
      },
      fontFamily: {
        // Heebo carries both scripts as one voice — it was drawn with
        // matching Hebrew and Latin letterforms, so Hebrew and Spanish/
        // English text on the same card don't read as two mismatched fonts.
        sans: ["Heebo", "ui-sans-serif", "system-ui", "sans-serif"],
        // Monospace exclusively for the phonetic transliteration line —
        // signals "sound this out character by character."
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      keyframes: {
        "reveal-glow": {
          "0%": { boxShadow: "0 0 0 0 rgba(242,153,74,0.55)", transform: "scale(0.97)", opacity: "0" },
          "60%": { boxShadow: "0 0 40px 8px rgba(242,153,74,0.35)" },
          "100%": { boxShadow: "0 0 0 0 rgba(242,153,74,0)", transform: "scale(1)", opacity: "1" },
        },
        "reveal-rise": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // Answer-feedback siblings of reveal-glow/reveal-rise, above — same
        // motif (a glow pulse), recolored per outcome rather than inventing
        // a new signature interaction for the answer moment.
        "correct-glow": {
          "0%": { boxShadow: "0 0 0 0 rgba(111,207,151,0.55)", transform: "scale(0.98)" },
          "60%": { boxShadow: "0 0 32px 6px rgba(111,207,151,0.35)" },
          "100%": { boxShadow: "0 0 0 0 rgba(111,207,151,0)", transform: "scale(1)" },
        },
        "incorrect-shake": {
          "0%, 100%": { transform: "translateX(0)" },
          "20%": { transform: "translateX(-6px)" },
          "40%": { transform: "translateX(5px)" },
          "60%": { transform: "translateX(-3px)" },
          "80%": { transform: "translateX(2px)" },
        },
      },
      animation: {
        "reveal-glow": "reveal-glow 550ms ease-out",
        "reveal-rise": "reveal-rise 400ms ease-out both",
        "correct-glow": "correct-glow 500ms ease-out",
        "incorrect-shake": "incorrect-shake 400ms ease-out",
      },
    },
  },
  plugins: [],
};
