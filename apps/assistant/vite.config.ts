import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { thirdPartyNotices } from "../../scripts/web/third-party-notices";

const ASSISTANT = "http://127.0.0.1:47800";

// A interface é servida pelo próprio Assistant em 127.0.0.1 (mesma origem da API: sem CORS).
// Em desenvolvimento, `npm run dev` repassa /api ao Assistant local e apresenta o pedido com a origem dele,
// porque a guarda da API recusa qualquer outra origem (AD-25) — inclusive a do servidor de desenvolvimento.
export default defineConfig({
  base: "/",
  plugins: [react(), thirdPartyNotices({ title: "Interface do SAFRA Assistant", publicPath: "/" })],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, assetsInlineLimit: 0 },
  server: {
    port: 5174,
    proxy: {
      "/api": {
        target: ASSISTANT,
        changeOrigin: true,
        configure: (proxy) => proxy.on("proxyReq", (request) => request.setHeader("origin", ASSISTANT)),
      },
    },
  },
  test: { environment: "jsdom", include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"] },
});
