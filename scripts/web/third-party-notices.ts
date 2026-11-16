import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

import type { Plugin } from "vite";

type LockEntry = {
  version?: string;
  license?: string;
  link?: boolean;
  resolved?: string;
  dependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
};

/**
 * O JavaScript compilado é entregue ao navegador de quem usa a interface: isso é distribuir o código das bibliotecas
 * incluídas, e as fontes também são distribuídas. As licenças (MIT, OFL) exigem que o aviso acompanhe as cópias.
 *
 * Este plugin percorre, no arquivo de trava único do workspace, as dependências de produção da interface (as
 * declaradas em "dependencies" e as delas, atravessando os pacotes do próprio workspace), reúne o texto da licença
 * de cada uma num arquivo publicado junto da interface e põe no início de cada script a indicação desse arquivo.
 */
export function thirdPartyNotices(options: { title: string; publicPath: string }): Plugin {
  const fileName = "licencas-de-terceiros.txt";
  return {
    name: "safra-avisos-de-licenca",
    apply: "build",
    generateBundle(_output, bundle) {
      const appDir = process.cwd();
      let root = appDir;
      while (!existsSync(join(root, "package-lock.json")) && dirname(root) !== root) root = dirname(root);
      const lock = JSON.parse(readFileSync(join(root, "package-lock.json"), "utf-8")) as { packages: Record<string, LockEntry> };
      const appKey = relative(root, appDir).split("\\").join("/");
      const app = JSON.parse(readFileSync(join(appDir, "package.json"), "utf-8")) as { dependencies?: Record<string, string> };

      const find = (name: string, from: string): [string, LockEntry] | undefined => {
        for (let base = from; ; base = base.includes("/node_modules/") ? base.slice(0, base.lastIndexOf("/node_modules/")) : "") {
          const key = base ? `${base}/node_modules/${name}` : `node_modules/${name}`;
          if (lock.packages[key]) return [key, lock.packages[key]];
          if (!base) return undefined;
        }
      };

      const seen = new Set<string>();
      const sections: string[] = [];
      let usesFonts = false;
      const queue: Array<[string, string]> = Object.keys(app.dependencies ?? {}).map((n) => [n, appKey]);
      while (queue.length) {
        const [name, from] = queue.shift() as [string, string];
        const found = find(name, from);
        if (!found) continue;
        let [key, entry] = found;
        if (seen.has(key)) continue;
        seen.add(key);
        if (entry.link && entry.resolved) {
          // pacote do próprio workspace: o código é deste projeto; seguem-se as dependências dele
          key = entry.resolved;
          entry = lock.packages[key] ?? {};
          if (name === "@safra/design-tokens") usesFonts = true;
          for (const dep of Object.keys({ ...entry.dependencies, ...entry.peerDependencies })) queue.push([dep, key]);
          continue;
        }
        const folder = join(root, key);
        const file = existsSync(folder) ? readdirSync(folder).find((f) => /^(licen[cs]e|copying)(\.(md|txt))?$/i.test(f)) : undefined;
        const text = file ? readFileSync(join(folder, file), "utf-8").trim()
          : `(arquivo de licença não encontrado; licença declarada: ${entry.license ?? "?"})`;
        sections.push(`${name} ${entry.version ?? ""} — ${entry.license ?? "?"}\n${"=".repeat(72)}\n${text}`);
        for (const dep of Object.keys({ ...entry.dependencies, ...entry.optionalDependencies })) queue.push([dep, key]);
      }
      if (usesFonts) {
        const fonts = resolve(root, "packages/design-tokens/fonts");
        for (const [family, license] of [["Inter", "OFL-inter.txt"], ["JetBrains Mono", "OFL-jetbrains-mono.txt"]] as const) {
          sections.push(`Fonte ${family} — OFL-1.1\n${"=".repeat(72)}\n${readFileSync(join(fonts, license), "utf-8").trim()}`);
        }
      }
      this.emitFile({ type: "asset", fileName, source: `${options.title} — licenças das bibliotecas e fontes incluídas na compilação\n\n${sections.join("\n\n")}\n` });
      for (const output of Object.values(bundle)) {
        if (output.type === "chunk") output.code = `/*! Licenças de terceiros: ${options.publicPath}${fileName} */\n${output.code}`;
      }
    },
  };
}
