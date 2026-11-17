import { chromium, expect, test, type Page } from '@playwright/test';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { completeOnboarding } from './helpers';
import { notebookPng } from './fixtures/images';

const BASE = 'http://127.0.0.1:5173';

/**
 * Usuário NEGOU a câmera para o site. Usa o Chromium completo (não o
 * "headless shell") e bloqueia a permissão pelo protocolo do navegador — o
 * mesmo estado de quem tocou em "Bloquear" no aviso de permissão.
 */
async function withBlockedCamera(run: (page: Page) => Promise<void>) {
  const context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), 'ce-camera-')), {
    channel: 'chromium',
    viewport: { width: 412, height: 915 },
    isMobile: true,
    hasTouch: true,
    args: ['--use-fake-device-for-media-stream'],
  });
  try {
    const cdp = await context.browser()?.newBrowserCDPSession();
    const page = context.pages()[0] ?? (await context.newPage());
    const session = cdp ?? (await context.newCDPSession(page));
    await session.send('Browser.setPermission', { permission: { name: 'camera' }, setting: 'denied', origin: BASE });
    await run(page);
  } finally {
    await context.close();
  }
}

test('permissão negada: explica como liberar e oferece a galeria', async () => {
  await withBlockedCamera(async (page) => {
    await page.goto(BASE);
    await completeOnboarding(page);
    await page.goto(`${BASE}/scanner`);
    await page.getByRole('button', { name: 'Abrir câmera' }).click();

    const camera = page.getByRole('dialog', { name: 'Câmera' });
    await expect(camera.getByText('Permissão da câmera negada')).toBeVisible({ timeout: 15_000 });
    await expect(camera.getByText(/Permissões → Câmera → Permitir/)).toBeVisible();
    await expect(camera.getByRole('button', { name: 'Tentar novamente' })).toBeVisible();
    await expect(camera.getByRole('button', { name: 'Fotografar página' })).toBeDisabled();

    // "Tentar novamente" continua respeitando o bloqueio (não trava a tela)
    await camera.getByRole('button', { name: 'Tentar novamente' }).click();
    await expect(camera.getByText('Permissão da câmera negada')).toBeVisible();

    // alternativa: galeria
    const chooser = page.waitForEvent('filechooser');
    await camera.getByRole('button', { name: 'Escolher da galeria' }).click();
    await (await chooser).setFiles({ name: 'pagina.png', mimeType: 'image/png', buffer: notebookPng(600, 800) });
    await expect(camera).toBeHidden();
    await expect(page.getByText('1 página pronta')).toBeVisible({ timeout: 30_000 });
  });
});

test('o erro real do navegador (NotAllowedError) também é reconhecido', async () => {
  await withBlockedCamera(async (page) => {
    await page.goto(BASE);
    const error = await page.evaluate(async () => {
      try {
        await navigator.mediaDevices.getUserMedia({ video: true });
        return 'ok';
      } catch (e) {
        return (e as Error).name;
      }
    });
    expect(error).toBe('NotAllowedError');
  });
});

test('câmera do sistema (input com capture) continua disponível', async ({ page }) => {
  await page.goto('/');
  await completeOnboarding(page);
  await page.goto('/scanner');
  const input = page.getByLabel('Fotografar com a câmera do aparelho');
  await expect(input).toHaveAttribute('capture', 'environment');
  await expect(input).toHaveAttribute('accept', 'image/*');
  await input.setInputFiles({ name: 'IMG_0001.png', mimeType: 'image/png', buffer: notebookPng(600, 800) });
  await expect(page.getByText('1 página pronta')).toBeVisible({ timeout: 30_000 });
});
