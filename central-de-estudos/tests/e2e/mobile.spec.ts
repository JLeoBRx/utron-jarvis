import { expect, test, type Page } from '@playwright/test';
import { completeOnboarding, expectCropAlignedWithImage, futureDate, trackConsoleErrors } from './helpers';
import { minimalPdf, notebookPng } from './fixtures/images';

/** Garante que a página não tem rolagem horizontal (layout cabe na tela). */
async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow, 'largura excedente em px').toBeLessThanOrEqual(0);
}

test('layout de celular: menu lateral em gaveta, sem rolagem horizontal', async ({ page }) => {
  const errors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-dashboard.png', fullPage: true });

  // Menu lateral fica escondido e abre como gaveta
  await expect(page.getByRole('navigation', { name: 'Menu principal' })).toBeHidden();
  await page.getByRole('button', { name: 'Abrir menu' }).click();
  const drawer = page.getByRole('dialog', { name: 'Menu' });
  await drawer.getByRole('link', { name: 'Disciplinas' }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Disciplinas', level: 1 })).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-disciplinas.png' });

  // Cadastro de prova pelo celular
  await page.getByRole('link', { name: 'Matemática 2' }).click();
  await page.getByRole('button', { name: 'Nova prova' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Nova prova' });
  await dialog.getByLabel('Nome da avaliação').fill('Avaliação 1');
  await dialog.getByLabel('Data').fill(futureDate(2));
  await dialog.getByRole('button', { name: 'Cadastrar prova' }).click();
  await expect(page.getByRole('heading', { name: 'Avaliação 1', level: 1 })).toBeVisible();
  await page.getByLabel('Adicionar conteúdos cobrados').fill('Funções');
  await page.keyboard.press('Enter');
  await expect(page.getByRole('list', { name: 'Conteúdos da prova' }).getByRole('listitem')).toHaveCount(1);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-prova.png', fullPage: true });

  // As abas rolam dentro do próprio contêiner, não a página
  await page.getByRole('link', { name: 'Desempenho' }).click();
  await expect(page).toHaveURL(/\/desempenho$/);
  await expectNoHorizontalScroll(page);
  expect(errors).toEqual([]);
});

test('celular: biblioteca, visualização de material e scanner cabem na tela', async ({ page }) => {
  const errors = trackConsoleErrors(page);
  await page.goto('/');
  await completeOnboarding(page);

  await page.goto('/biblioteca');
  await expectNoHorizontalScroll(page);
  await page.getByRole('button', { name: 'Enviar arquivos' }).first().click();
  const dialog = page.getByRole('dialog', { name: 'Enviar materiais' });
  await dialog.getByLabel('Arquivos para enviar').setInputFiles({ name: 'aula.pdf', mimeType: 'application/pdf', buffer: minimalPdf('Aula') });
  await dialog.getByLabel('Disciplina').selectOption({ label: 'Física 2' });
  await dialog.getByRole('button', { name: 'Enviar' }).click();
  await expect(page.getByText('1 material enviado.')).toBeVisible();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-biblioteca.png' });

  // PDF renderizado no celular (o Chrome do Android não exibe PDF embutido)
  await page.getByRole('link', { name: /aula/ }).click();
  await expect(page.getByTestId('pdf-viewer').locator('canvas')).toHaveCount(1);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-material.png', fullPage: true });

  await page.goto('/scanner');
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-scanner-inicio.png' });
  await page.getByLabel('Escolher fotos da galeria').setInputFiles([
    { name: 'p1.png', mimeType: 'image/png', buffer: notebookPng(600, 800, 0) },
    { name: 'p2.png', mimeType: 'image/png', buffer: notebookPng(600, 800, 1) },
  ]);
  await expect(page.getByText('2 páginas prontas')).toBeVisible({ timeout: 30_000 });
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-scanner-paginas.png' });
  await page.getByRole('button', { name: 'Editar página 1' }).first().click();
  await expect(page.getByTestId('editor-result')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('radio', { name: 'Recorte' }).click();
  await expect(page.getByRole('slider', { name: 'Canto inferior direito' })).toBeVisible();
  await expectCropAlignedWithImage(page);
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-scanner-editor.png' });
  await page.getByRole('button', { name: 'Aplicar' }).click();
  await page.getByRole('button', { name: /Revisar e salvar/ }).click();
  await expectNoHorizontalScroll(page);
  await page.screenshot({ path: 'tests/e2e/.artifacts/mobile-scanner-revisar.png' });
  expect(errors).toEqual([]);
});
