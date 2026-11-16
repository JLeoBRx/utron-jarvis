// Teste de ponta a ponta do SAFRA Portal num navegador real (Chromium via Playwright), contra o servidor real
// com o painel compilado. Iniciado por scripts/e2e/portal_e2e.py, que cria o banco temporário e o administrador.
//
// Variáveis: PORTAL_URL, ADMIN_EMAIL, ADMIN_PASSWORD, SHOTS_DIR (opcional: capturas para a documentação).
import { strict as assert } from "node:assert";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";

// require() respeita NODE_PATH: funciona com o Playwright instalado no projeto ou no sistema.
const { chromium } = createRequire(import.meta.url)("playwright");

const BASE = process.env.PORTAL_URL;
const EMAIL = process.env.ADMIN_EMAIL;
const PASSWORD = process.env.ADMIN_PASSWORD;
const SHOTS = process.env.SHOTS_DIR || "";
if (!BASE || !EMAIL || !PASSWORD) throw new Error("defina PORTAL_URL, ADMIN_EMAIL e ADMIN_PASSWORD");
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const results = [];
async function step(name, work) {
  const started = Date.now();
  try {
    await work();
    results.push({ name, ok: true, ms: Date.now() - started });
    console.log(`ok   ${name}`);
  } catch (error) {
    results.push({ name, ok: false, ms: Date.now() - started, error: String(error && error.message || error) });
    console.log(`FALHOU ${name}\n     ${String(error && error.stack || error).split("\n").slice(0, 4).join("\n     ")}`);
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const consoleErrors = [];
page.on("console", (m) => { if (m.type() === "error" && !/status of (401|404|422|409)/.test(m.text())) consoleErrors.push(m.text()); });
page.on("pageerror", (e) => consoleErrors.push(String(e)));
const shot = async (name, target = page) => { if (SHOTS) await target.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }); };
const slug = `e2e-${Date.now().toString(36)}`;

await step("visitante vê o site público e não entra no painel", async () => {
  const home = await page.goto(BASE + "/");
  assert.equal(home.status(), 200);
  assert.equal(await page.locator("h1").count(), 1);
  const api = await page.request.get(BASE + "/admin/api/pages");
  assert.equal(api.status(), 401);
  await page.goto(BASE + "/admin/");
  await page.getByRole("heading", { name: "Painel administrativo" }).waitFor();
  await shot("admin-entrada");
});

await step("teclado: o primeiro Tab do site leva ao atalho para o conteúdo", async () => {
  await page.goto(BASE + "/sobre");
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.textContent);
  assert.match(focused || "", /Pular para o conteúdo/);
});

await step("senha errada é recusada com mensagem genérica", async () => {
  await page.goto(BASE + "/admin/");
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill("senha errada de proposito");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("alert").filter({ hasText: "E-mail ou senha incorretos." }).waitFor();
});

await step("administrador entra e vê o resumo", async () => {
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("heading", { name: "Resumo" }).waitFor();
  await page.getByText("Páginas publicadas").waitFor();
  const cookies = await context.cookies();
  const session = cookies.find((c) => c.name === "safra_portal_session");
  assert.ok(session && session.httpOnly && session.sameSite === "Strict" && session.path === "/admin");
  await shot("admin-resumo");
});

await step("criar página como rascunho: não aparece no site", async () => {
  await page.goto(BASE + "/admin/#/pages/novo");
  await page.getByLabel("Título", { exact: true }).fill("Página do teste de ponta a ponta");
  await page.getByLabel("Endereço (slug)").fill(slug);
  await page.getByLabel("Texto", { exact: true }).fill("Primeira versão do texto.");
  await page.getByRole("button", { name: "Criar rascunho" }).click();
  await page.getByText("rascunho", { exact: true }).first().waitFor();
  const response = await page.request.get(`${BASE}/${slug}`);
  assert.equal(response.status(), 404);
  await shot("admin-editor");
});

await step("publicar: a página entra no ar", async () => {
  await page.getByRole("button", { name: "Publicar", exact: true }).click();
  await page.getByText("Publicado. A versão mais recente está no ar.").waitFor();
  const visitor = await browser.newPage();
  const response = await visitor.goto(`${BASE}/${slug}`);
  assert.equal(response.status(), 200);
  assert.ok((await visitor.content()).includes("Primeira versão do texto."));
  await visitor.close();
});

await step("editar depois de publicar: o público continua vendo a versão publicada", async () => {
  await page.getByLabel("Texto", { exact: true }).fill("Segunda versão, ainda não publicada.");
  await page.getByRole("button", { name: "Salvar rascunho" }).click();
  await page.getByText("Rascunho salvo como nova versão.").waitFor();
  const html = await (await page.request.get(`${BASE}/${slug}`)).text();
  assert.ok(html.includes("Primeira versão do texto.") && !html.includes("Segunda versão"));
});

await step("restaurar a versão 1 como rascunho", async () => {
  await page.getByRole("button", { name: "v1" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Restaurar como rascunho" }).click();
  await page.getByText("Versão 1 restaurada como rascunho.").waitFor();
  await page.getByRole("button", { name: "v3" }).waitFor();
  assert.equal(await page.getByLabel("Texto", { exact: true }).inputValue(), "Primeira versão do texto.");
});

await step("texto com HTML e script vira texto no site", async () => {
  await page.getByLabel("Texto", { exact: true }).fill('<script>window.__xss = 1</script><img src=x onerror="window.__xss = 2">');
  await page.getByRole("button", { name: "Salvar rascunho" }).click();
  await page.getByText("Rascunho salvo como nova versão.").waitFor();
  await page.getByRole("button", { name: "Publicar alterações" }).click();
  await page.getByText("Publicado. A versão mais recente está no ar.").waitFor();
  const visitor = await browser.newPage();
  await visitor.goto(`${BASE}/${slug}`);
  assert.equal(await visitor.evaluate(() => window.__xss), undefined);
  assert.ok((await visitor.locator("main p").allTextContents()).some((t) => t.includes("<script>")));
  await visitor.close();
});

await step("envio de arquivo que não é imagem é recusado", async () => {
  await page.goto(BASE + "/admin/#/media");
  await page.getByLabel("Arquivo").setInputFiles({ name: "falso.png", mimeType: "image/png", buffer: Buffer.from("<?php echo 1; ?>") });
  await page.getByRole("button", { name: "Enviar" }).click();
  await page.getByRole("alert").filter({ hasText: "Tipo de arquivo não aceito" }).waitFor();
  await page.getByText("Nenhuma imagem na biblioteca.").waitFor();
});

await step("publicação de instaladores aparece bloqueada", async () => {
  await page.goto(BASE + "/admin/#/releases");
  await page.getByText("Publicação bloqueada.").waitFor();
  await page.getByLabel("Número da versão").fill("4.0.0-beta.1");
  await page.getByRole("button", { name: "Cadastrar" }).click();
  await page.getByRole("cell", { name: "4.0.0-beta.1" }).waitFor();
  await page.getByRole("button", { name: "Publicar" }).click();
  await page.getByRole("alert").filter({ hasText: "bloqueada" }).waitFor();
});

await step("excluir com confirmação: sai do site", async () => {
  await page.goto(BASE + "/admin/#/pages");
  await page.getByRole("link", { name: "Página do teste de ponta a ponta" }).click();
  await page.getByRole("button", { name: "Excluir página" }).click();
  const dialog = page.getByRole("dialog");
  assert.equal(await dialog.getByRole("button", { name: "Excluir" }).isDisabled(), true);
  await dialog.getByLabel("Endereço").fill(slug);
  await dialog.getByRole("button", { name: "Excluir" }).click();
  await page.getByRole("heading", { name: "Páginas" }).waitFor();
  assert.equal((await page.request.get(`${BASE}/${slug}`)).status(), 404);
});

await step("celular (390 px): sem rolagem lateral no site e no painel", async () => {
  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, storageState: await context.storageState() });
  const phone = await mobile.newPage();
  for (const path of ["/", "/funcionalidades", "/admin/#/", "/admin/#/pages"]) {
    await phone.goto(BASE + path);
    await phone.waitForLoadState("networkidle");
    const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(overflow <= 1, `${path} tem ${overflow}px de rolagem lateral`);
  }
  await phone.goto(BASE + "/admin/#/");
  await shot("admin-resumo-390", phone);
  await mobile.close();
});

await step("sair encerra a sessão no servidor", async () => {
  await page.goto(BASE + "/admin/#/");
  await page.getByRole("button", { name: "Sair" }).click();
  await page.getByRole("heading", { name: "Painel administrativo" }).waitFor();
  assert.equal((await page.request.get(BASE + "/admin/api/auth/session")).status(), 401);
});

await step("nenhum erro de JavaScript nem bloqueio de CSP no console", async () => {
  assert.deepEqual(consoleErrors, []);
});

await browser.close();
const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length} de ${results.length} etapas aprovadas`);
console.log("RESULT=" + JSON.stringify(results));
process.exit(failed.length ? 1 : 0);
