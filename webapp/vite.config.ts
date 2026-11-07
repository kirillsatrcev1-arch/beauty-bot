import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Обычная сборка кладётся в app/web/dist и раздаётся Python-сервером.
// Демо-сборка (--mode demo) работает без сервера, на встроенных примерах данных.
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === "demo" ? "./" : "/",
  build: {
    outDir: mode === "demo" ? "dist-demo" : "../app/web/dist",
    emptyOutDir: true,
    assetsInlineLimit: 0,
  },
  server: { proxy: { "/api": "http://127.0.0.1:8080", "/media": "http://127.0.0.1:8080", "/uploads": "http://127.0.0.1:8080", "/ics": "http://127.0.0.1:8080" } },
}));
