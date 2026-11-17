import { expect, test } from '@playwright/test';
import { completeOnboarding, trackConsoleErrors } from './helpers';

/**
 * Câmera REAL do navegador (getUserMedia) com permissão concedida. O Chromium
 * usa uma câmera falsa que transmite um vídeo sintético de uma página de
 * caderno (ver playwright.config.ts). Roda no desktop e em celular emulado.
 */
test('fotografa várias páginas em sequência pela câmera e salva na disciplina', async ({ page }) => {
  const errors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);
  await page.goto('/disciplinas');
  await page.getByRole('link', { name: 'Química 2' }).click();
  await page.getByRole('link', { name: 'Fotografar caderno' }).click();
  await expect(page).toHaveURL(/\/scanner\?disciplina=/);

  await page.getByRole('button', { name: 'Abrir câmera' }).click();
  const camera = page.getByRole('dialog', { name: 'Câmera' });
  const video = camera.getByTestId('camera-video');
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState >= 2 && v.videoWidth > 0), { timeout: 15_000 }).toBe(true);

  const shutter = camera.getByRole('button', { name: 'Fotografar página' });
  await shutter.click();
  await expect(camera.getByText('1 página')).toBeVisible();
  await shutter.click();
  await expect(camera.getByText('2 páginas')).toBeVisible();
  await camera.getByRole('button', { name: 'Concluir' }).click();
  await expect(camera).toBeHidden();

  // a câmera é liberada ao fechar (nenhuma faixa de vídeo ativa)
  expect(await page.evaluate(() => document.querySelectorAll('video').length)).toBe(0);

  await expect(page.getByText('2 páginas prontas')).toBeVisible({ timeout: 30_000 });
  // o quadro sintético tem a folha sobre a mesa → recorte automático aplicado
  await expect(page.getByTestId('scanner-page').getByText('recortada')).toHaveCount(2);

  await page.getByRole('button', { name: /Revisar e salvar/ }).click();
  await expect(page.getByLabel('Disciplina')).not.toHaveValue('');
  await page.getByRole('button', { name: 'Salvar caderno' }).click();
  await expect(page.getByRole('heading', { name: 'Caderno salvo!' })).toBeVisible({ timeout: 60_000 });
  await page.getByRole('link', { name: 'Ver o caderno salvo' }).click();
  await expect(page.getByTestId('scan-page')).toHaveCount(2);
  await expect(page.getByTestId('scan-page').first().getByText(/Câmera/)).toBeVisible();
  expect(errors).toEqual([]);
});
