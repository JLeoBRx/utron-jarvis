import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// O painel é servido pelo próprio Portal em /admin/ (mesma origem da API: sem CORS, cookie SameSite=Strict).
// Em desenvolvimento, `npm run dev` repassa /admin/api, /media e /static ao Portal local.
export default defineConfig({
  base: "/admin/",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, assetsInlineLimit: 0 },
  server: {
    port: 5173,
    proxy: {
      "/admin/api": "http://127.0.0.1:47900",
      "/admin/preview": "http://127.0.0.1:47900",
      "/media": "http://127.0.0.1:47900",
      "/static": "http://127.0.0.1:47900",
    },
  },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"] },
});
