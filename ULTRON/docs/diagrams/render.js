// Renderiza docs/diagrams/src/*.mmd em SVG e PNG com o Mermaid, no Chromium do Playwright.
// Uso: node render.js <pasta src> <pasta de saída> <caminho do mermaid.min.js>   (ver docs/README.md)
const fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
(async () => {
  const [src, out, lib] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2, viewport: { width: 2400, height: 1600 } });
  await page.setContent('<html><body style="margin:0;background:#fff"><div id="c"></div></body></html>');
  await page.addScriptTag({ path: lib });
  await page.evaluate(() => mermaid.initialize({ startOnLoad: false, theme: 'neutral', fontFamily: 'Arial, Helvetica, sans-serif',
    flowchart: { htmlLabels: true, curve: 'basis' }, securityLevel: 'strict' }));
  for (const f of fs.readdirSync(src).filter(f => f.endsWith('.mmd')).sort()) {
    const code = fs.readFileSync(path.join(src, f), 'utf8');
    const name = f.replace(/\.mmd$/, '');
    const svg = await page.evaluate(async ([id, c]) => (await mermaid.render(id, c)).svg, ['d' + name.replace(/\W/g, ''), code]);
    fs.writeFileSync(path.join(out, name + '.svg'), svg);
    await page.setContent(`<html><body style="margin:0;background:#fff;display:inline-block">${svg}</body></html>`);
    await page.evaluate(() => { const s = document.querySelector('svg'); const mw = parseFloat(s.style.maxWidth) || s.getBBox().width;
      s.removeAttribute('width'); s.style.width = mw + 'px'; s.style.maxWidth = 'none'; });
    const el = await page.$('svg');
    await el.screenshot({ path: path.join(out, name + '.png'), omitBackground: false });
    await page.setContent('<html><body style="margin:0;background:#fff"><div id="c"></div></body></html>');
    await page.addScriptTag({ path: lib });
    await page.evaluate(() => mermaid.initialize({ startOnLoad: false, theme: 'neutral', fontFamily: 'Arial, Helvetica, sans-serif',
      flowchart: { htmlLabels: true, curve: 'basis' }, securityLevel: 'strict' }));
    console.log('ok', name);
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
