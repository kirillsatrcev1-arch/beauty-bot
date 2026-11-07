/** Дизайн-токены: цвета из CSS-переменных, чтобы светлая и тёмная темы переключались без перерисовки классов */
const c = (v) => `rgb(var(--${v}) / <alpha-value>)`;
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: c("bg"), surface: c("surface"), primary: c("primary"), secondary: c("secondary"),
        accent: c("accent"), ink: c("ink"), muted: c("muted"), line: c("line"), soft: c("soft"),
        ok: c("ok"), warn: c("warn"), danger: c("danger"),
      },
      fontFamily: {
        display: ['"Cormorant Garamond"', "Cormorant", "Georgia", "serif"],
        sans: ["Onest", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
      },
      borderRadius: { xl2: "20px", xl3: "28px" },
      boxShadow: {
        card: "0 1px 2px rgb(var(--shadow) / .04), 0 12px 32px -14px rgb(var(--shadow) / .22)",
        lift: "0 20px 44px -18px rgb(var(--shadow) / .38)",
        tab: "0 10px 40px -12px rgb(var(--shadow) / .35)",
      },
      transitionTimingFunction: { soft: "cubic-bezier(.22,.8,.24,1)" },
    },
  },
  plugins: [],
};
