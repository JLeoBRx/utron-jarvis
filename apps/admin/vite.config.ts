import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const NOTICE_FILE = "licencas-de-terceiros.txt";

/**
 * O JavaScript compilado é entregue ao navegador de quem usa o painel: isso é distribuir o código das bibliotecas
 * incluídas. As licenças delas (MIT) exigem que o aviso acompanhe as cópias. Este plugin reúne o texto da licença
 * de cada dependência de produção (as que não são "dev" no arquivo de trava) num arquivo publicado junto do painel
 * e põe no início de cada script a indicação desse arquivo.
 */
function thirdPartyNotices(): Plugin {
  return {
    name: "safra-avisos-de-licenca",
    apply: "build",
    generateBundle(_options, bundle) {
      const lock = JSON.parse(readFileSync("package-lock.json", "utf-8")) as { packages: Record<string, { dev?: boolean; version?: string; license?: string }> };
      const sections: string[] = [];
      for (const [path, info] of Object.entries(lock.packages)) {
        if (!path.startsWith("node_modules/") || info.dev) continue;
        const name = path.slice("node_modules/".length);
        const folder = join("node_modules", name);
        const file = readdirSync(folder).find((f: string) => /^(licen[cs]e|copying)(\.(md|txt))?$/i.test(f));
        const text = file ? readFileSync(join(folder, file), "utf-8").trim() : `(arquivo de licença não encontrado; licença declarada: ${info.license ?? "?"})`;
        sections.push(`${name} ${info.version ?? ""} — ${info.license ?? "?"}\n${"=".repeat(72)}\n${text}`);
      }
      this.emitFile({ type: "asset", fileName: NOTICE_FILE,
        source: `Painel administrativo do SAFRA — licenças das bibliotecas incluídas na compilação\n\n${sections.join("\n\n")}\n` });
      for (const output of Object.values(bundle)) {
        if (output.type === "chunk") output.code = `/*! Licenças de terceiros: /admin/${NOTICE_FILE} */\n${output.code}`;
      }
    },
  };
}

// O painel é servido pelo próprio Portal em /admin/ (mesma origem da API: sem CORS, cookie SameSite=Strict).
// Em desenvolvimento, `npm run dev` repassa /admin/api, /media e /static ao Portal local.
export default defineConfig({
  base: "/admin/",
  plugins: [react(), thirdPartyNotices()],
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
