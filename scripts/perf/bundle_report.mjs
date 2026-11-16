// Tamanho do que cada interface compilada entrega ao navegador: bruto e comprimido (gzip, nível 9).
// Uso: node scripts/perf/bundle_report.mjs [--json saida.json]   (depois de `npm run build`)
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const apps = [["Painel administrativo", "apps/admin/dist"], ["Interface do Assistant", "apps/assistant/dist"]];
const kind = (name) => (name.endsWith(".js") ? "JavaScript" : name.endsWith(".css") ? "CSS" : name.endsWith(".woff2") ? "fontes" : name.endsWith(".html") ? "HTML" : "outros");
const report = [];
for (const [label, dir] of apps) {
  let files;
  try { files = [...readdirSync(dir), ...readdirSync(join(dir, "assets")).map((f) => join("assets", f))]; } catch { continue; }
  const totals = {};
  for (const file of files) {
    const path = join(dir, file);
    if (!statSync(path).isFile() || file.endsWith(".txt")) continue;
    const data = readFileSync(path);
    const k = kind(file);
    totals[k] ??= { raw: 0, gzip: 0, files: 0 };
    totals[k].raw += data.length;
    totals[k].gzip += k === "fontes" ? data.length : gzipSync(data, { level: 9 }).length;
    totals[k].files += 1;
  }
  report.push({ app: label, totals });
}
const kb = (n) => (n / 1024).toFixed(1);
const lines = ["| Interface | Tipo | Arquivos | Bruto (kB) | Comprimido (kB) |", "|---|---|---|---|---|"];
for (const { app, totals } of report) for (const [k, t] of Object.entries(totals)) lines.push(`| ${app} | ${k} | ${t.files} | ${kb(t.raw)} | ${kb(t.gzip)} |`);
console.log("### Tamanho das interfaces compiladas\n\n" + lines.join("\n") + "\n\nFontes woff2 já vêm comprimidas; o valor comprimido delas é o próprio arquivo.");
const out = process.argv.indexOf("--json");
if (out > 0) writeFileSync(process.argv[out + 1], JSON.stringify(report, null, 1));
